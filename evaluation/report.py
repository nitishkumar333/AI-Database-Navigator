"""Aggregates scored prediction records into summary.json and report.md."""
import json
import statistics
from collections import Counter
from pathlib import Path

from evaluation.dataset import DIFFICULTIES

_METRICS = (
    ("ex", "EX (BIRD official)"),
    ("ex_column_tolerant", "EX (column-tolerant)"),
    ("soft_f1", "Soft-F1"),
)


def _bucket(records: list[dict]) -> dict:
    scorable = [r for r in records if r.get("status") != "gold_error"]
    n = len(scorable)
    out = {"count": n}
    for key, _ in _METRICS:
        values = [float(r["metrics"][key]) for r in scorable]
        out[key] = round(100 * sum(values) / n, 2) if n else None
    return out


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    return round(values[min(len(values) - 1, int(pct * len(values)))], 3)


def summarize(records: list[dict], run_config: dict) -> dict:
    records = sorted(records, key=lambda r: r["question_id"])
    by_difficulty = {d: _bucket([r for r in records if r["difficulty"] == d]) for d in DIFFICULTIES}
    by_difficulty["total"] = _bucket(records)
    by_db = {
        db: _bucket([r for r in records if r["db_id"] == db])
        for db in sorted({r["db_id"] for r in records})
    }

    usage = [r.get("usage") or {} for r in records]
    latencies = [r["latency_s"] for r in records if r.get("latency_s") is not None]
    multi_attempt = [r for r in records if len(r.get("attempted_sql") or []) > 1]
    n = len(records) or 1

    return {
        "run": run_config,
        "questions": len(records),
        "accuracy_by_difficulty": by_difficulty,
        "accuracy_by_db": by_db,
        "status_counts": dict(Counter(r.get("status", "unscored") for r in records).most_common()),
        "cost": {
            "input_tokens": sum(u.get("input_tokens", 0) for u in usage),
            "output_tokens": sum(u.get("output_tokens", 0) for u in usage),
            "avg_tokens_per_question": round(sum(u.get("total_tokens", 0) for u in usage) / n, 1),
            "avg_llm_calls_per_question": round(sum(r.get("llm_calls", 0) for r in records) / n, 2),
        },
        "latency_s": {
            "mean": round(statistics.mean(latencies), 3) if latencies else None,
            "p50": _percentile(latencies, 0.5),
            "p95": _percentile(latencies, 0.95),
        },
        "self_correction": {
            "questions_with_retries": len(multi_attempt),
            "correct_after_retry": sum(1 for r in multi_attempt if r.get("status") == "correct"),
        },
    }


def _fmt(v) -> str:
    return "-" if v is None else f"{v:.2f}"


def render_markdown(summary: dict) -> str:
    run = summary["run"]
    diff = summary["accuracy_by_difficulty"]
    cols = [*DIFFICULTIES, "total"]
    lines = [
        f"# SQL Agent Evaluation: `{run.get('run_name')}`",
        "",
        f"- **Provider / model:** {run.get('provider')} / `{run.get('model')}`",
        f"- **Dataset:** {run.get('dataset')} ({summary['questions']} questions scored)",
        f"- **Evidence hints:** {'on' if run.get('use_evidence') else 'off'}  "
        f"| **Schema scope:** {'all BIRD tables' if run.get('full_schema') else 'per-database'}",
        f"- **Started:** {run.get('started_at')}",
        "",
        "## Accuracy (%)",
        "",
        "| Metric | " + " | ".join(cols) + " |",
        "|---|" + "---:|" * len(cols),
        "| Count | " + " | ".join(str(diff[c]["count"]) for c in cols) + " |",
    ]
    for key, label in _METRICS:
        lines.append(f"| {label} | " + " | ".join(_fmt(diff[c][key]) for c in cols) + " |")

    lines += ["", "## By database", "", "| db_id | n | EX | EX (col-tolerant) | Soft-F1 |", "|---|---:|---:|---:|---:|"]
    for db, b in summary["accuracy_by_db"].items():
        lines.append(f"| {db} | {b['count']} | {_fmt(b['ex'])} | {_fmt(b['ex_column_tolerant'])} | {_fmt(b['soft_f1'])} |")

    lines += ["", "## Outcome breakdown", "", "| Status | Count |", "|---|---:|"]
    lines += [f"| {k} | {v} |" for k, v in summary["status_counts"].items()]

    cost, lat, sc = summary["cost"], summary["latency_s"], summary["self_correction"]
    lines += [
        "",
        "## Cost & behaviour",
        "",
        f"- Tokens: {cost['input_tokens']:,} in / {cost['output_tokens']:,} out "
        f"(avg {cost['avg_tokens_per_question']:,} per question)",
        f"- Avg LLM calls per question: {cost['avg_llm_calls_per_question']}",
        f"- Latency: mean {lat['mean']}s, p50 {lat['p50']}s, p95 {lat['p95']}s",
        f"- Questions where the agent retried after a tool error: {sc['questions_with_retries']} "
        f"({sc['correct_after_retry']} ended correct)",
        "",
        "Status legend: `correct` = EX match; `wrong_result` = ran but rows differ; "
        "`no_sql` = agent never produced a successful query; `pred_error`/`pred_timeout` = "
        "generated SQL failed on re-execution; `agent_error` = graph/LLM error; "
        "`gold_error` = gold SQL failed (excluded from accuracy).",
    ]
    return "\n".join(lines) + "\n"


def write_report(run_dir: Path, records: list[dict], run_config: dict) -> dict:
    summary = summarize(records, run_config)
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (run_dir / "report.md").write_text(render_markdown(summary), encoding="utf-8")

    failures = [r for r in sorted(records, key=lambda r: r["question_id"]) if r.get("status") != "correct"]
    with open(run_dir / "failures.jsonl", "w", encoding="utf-8") as f:
        for r in failures:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    return summary
