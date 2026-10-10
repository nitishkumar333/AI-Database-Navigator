"""Runs the production SQLAgent (in evaluation mode) over BIRD examples and
scores each generated query against the gold SQL."""
import logging
import re
import threading
import time
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy.engine import Engine

from app.services.sql_agent import AGENT_MODE_EVALUATION, SQLAgent
from evaluation import metrics
from evaluation.dataset import Example
from evaluation.db import ExecResult, build_schema_context, execute_sql

logger = logging.getLogger(__name__)

_MAX_BACKOFF_S = 300

# Retry hints in provider 429 messages:
#   Gemini: 'retryDelay': '47960s'      Groq: "Please try again in 1m2.5s"
_GEMINI_RETRY = re.compile(r"retryDelay'?\"?:\s*'?\"?(\d+(?:\.\d+)?)s")
_GROQ_RETRY = re.compile(r"try again in\s+((?:\d+(?:\.\d+)?[hms])+)")


def _provider_retry_after(message: str) -> float | None:
    """Seconds the provider asked us to wait, if its error says so."""
    if m := _GEMINI_RETRY.search(message):
        return float(m.group(1))
    if m := _GROQ_RETRY.search(message):
        units = {"h": 3600, "m": 60, "s": 1}
        return sum(float(n) * units[u] for n, u in re.findall(r"(\d+(?:\.\d+)?)([hms])", m.group(1)))
    return None


class RateLimitExhausted(RuntimeError):
    """Provider kept returning 429 after all retries. The run stops and the
    current question stays unrecorded, so a resumed run will retry it."""


class RateLimiter:
    """Spaces request *starts* at least 60/rpm seconds apart, across threads."""

    def __init__(self, rpm: float | None):
        self.interval = 60.0 / rpm if rpm and rpm > 0 else 0.0
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self) -> None:
        if not self.interval:
            return
        with self._lock:
            now = time.monotonic()
            start = max(now, self._next)
            self._next = start + self.interval
        if start > now:
            time.sleep(start - now)


@dataclass
class RunOptions:
    use_evidence: bool = True
    full_schema: bool = False
    rpm: float | None = None
    max_rate_limit_retries: int = 6
    backoff_base_s: float = 15.0
    exec_timeout_ms: int = 60_000
    float_precision: int = 4
    max_output_rows: int = 100  # rows of gold/pred output stored per record; 0 = all


class AgentEvaluator:
    def __init__(self, engine: Engine, llm, db_tables: dict[str, list[str]], opts: RunOptions):
        self.engine = engine
        self.llm = llm
        self.db_tables = db_tables
        self.opts = opts
        self.limiter = RateLimiter(opts.rpm)
        self._agents: dict[str, SQLAgent] = {}
        self._agents_lock = threading.Lock()
        self._gold_cache: dict[int, ExecResult] = {}

    # ── Agent ────────────────────────────────────────────────────────────────

    def _agent_for(self, db_id: str) -> SQLAgent:
        key = "__all__" if self.opts.full_schema else db_id
        with self._agents_lock:
            if key not in self._agents:
                if self.opts.full_schema:
                    tables = sorted({t for ts in self.db_tables.values() for t in ts})
                else:
                    tables = self.db_tables[db_id]
                schema = build_schema_context(self.engine, tables)
                self._agents[key] = SQLAgent(
                    self.engine, schema, mode=AGENT_MODE_EVALUATION, llm=self.llm
                )
            return self._agents[key]

    def predict(self, ex: Example) -> dict:
        agent = self._agent_for(ex.db_id)
        prompt = ex.prompt(self.opts.use_evidence)

        for attempt in range(self.opts.max_rate_limit_retries + 1):
            self.limiter.wait()
            start = time.perf_counter()
            try:
                result = agent.run_query(prompt, user_id=0, conn_id=0)
                break
            except HTTPException as exc:
                # run_query turns provider rate-limit errors into a 429.
                if exc.status_code != 429:
                    raise
                provider_error = str(exc.__context__ or exc)
                retry_after = _provider_retry_after(provider_error)
                if retry_after and retry_after > _MAX_BACKOFF_S:
                    # e.g. a daily quota: no point sleeping through it.
                    raise RateLimitExhausted(
                        f"provider asks to wait {retry_after / 3600:.1f}h (quota exhausted?)"
                    ) from exc
                if attempt == self.opts.max_rate_limit_retries:
                    raise RateLimitExhausted(provider_error[:300]) from exc
                delay = max(
                    min(self.opts.backoff_base_s * 2 ** attempt, _MAX_BACKOFF_S),
                    retry_after or 0,
                )
                logger.warning("Rate limited on q%s; retrying in %.0fs", ex.question_id, delay)
                time.sleep(delay)
        latency = time.perf_counter() - start

        trace = result.get("trace") or {}
        return {
            "question_id": ex.question_id,
            "db_id": ex.db_id,
            "difficulty": ex.difficulty,
            "question": ex.question,
            "evidence": ex.evidence,
            "prompt": prompt,
            "gold_sql": ex.gold_sql,
            "pred_sql": result.get("generated_sql", ""),
            "agent_error": None if result.get("success") else result.get("error"),
            "attempted_sql": trace.get("attempted_sql", []),
            "tool_errors": trace.get("tool_errors", []),
            "llm_calls": trace.get("llm_calls", 0),
            "usage": trace.get("usage", {}),
            "final_text": trace.get("final_text", "") if not result.get("generated_sql") else "",
            "latency_s": round(latency, 3),
        }

    # ── Scoring ──────────────────────────────────────────────────────────────

    def _gold(self, question_id: int, sql: str) -> ExecResult:
        if question_id not in self._gold_cache:
            self._gold_cache[question_id] = execute_sql(
                self.engine, sql, timeout_ms=self.opts.exec_timeout_ms
            )
        return self._gold_cache[question_id]

    def _output(self, rows: list) -> tuple[list[list], bool]:
        """Result rows to store in the record, capped at opts.max_output_rows
        (0 = no cap). Values are kept as-is; the JSONL writer str()s
        Decimal/date/etc."""
        limit = self.opts.max_output_rows
        if limit and len(rows) > limit:
            return [list(r) for r in rows[:limit]], True
        return [list(r) for r in rows], False

    def score(self, rec: dict) -> dict:
        """Adds execution results, metrics and a status to a prediction record."""
        gold = self._gold(rec["question_id"], rec["gold_sql"])
        # Records from older runs stored 5-row samples instead of outputs.
        rec.pop("gold_sample", None)
        rec.pop("pred_sample", None)
        rec["gold_row_count"] = len(gold.rows) if gold.ok else None
        rec["gold_columns"] = gold.columns
        rec["gold_sql_output"], rec["gold_output_truncated"] = self._output(gold.rows)
        rec["gold_error"] = gold.error
        for key in ("pred_row_count", "pred_columns", "pred_sql_output",
                    "pred_output_truncated", "pred_error"):
            rec[key] = None
        rec["metrics"] = {"ex": False, "ex_column_tolerant": False, "soft_f1": 0.0}

        if not gold.ok:
            rec["status"] = "gold_error"
            return rec
        if rec.get("agent_error") and not rec.get("pred_sql"):
            rec["status"] = "agent_error"
            return rec
        if not rec.get("pred_sql"):
            rec["status"] = "no_sql"
            return rec

        pred = execute_sql(self.engine, rec["pred_sql"], timeout_ms=self.opts.exec_timeout_ms)
        if not pred.ok:
            rec["pred_error"] = pred.error
            rec["status"] = "pred_timeout" if pred.timed_out else "pred_error"
            return rec

        rec["pred_row_count"] = len(pred.rows)
        rec["pred_columns"] = pred.columns
        rec["pred_sql_output"], rec["pred_output_truncated"] = self._output(pred.rows)
        rec["metrics"] = metrics.score(pred.rows, gold.rows, self.opts.float_precision)
        rec["status"] = "correct" if rec["metrics"]["ex"] else "wrong_result"
        return rec

    def evaluate(self, ex: Example) -> dict:
        return self.score(self.predict(ex))
