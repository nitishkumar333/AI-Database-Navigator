"""
Offline evaluation of the SQL agent on BIRD mini-dev (PostgreSQL).

    python -m evaluation check-gold                 # sanity-check dataset + DB, no LLM calls
    python -m evaluation run --provider groq --sample 50
    python -m evaluation run --run-name my-run      # resumes an interrupted run
    python -m evaluation score --run-name my-run    # re-score without LLM calls

Run from the repository root with the backend virtualenv.
"""
from evaluation import bootstrap  # noqa: F401  (must precede `app` imports)

import argparse
import json
import logging
import os
import re
import sys
import threading
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime
from pathlib import Path

import sqlglot
from sqlalchemy import inspect
from sqlalchemy.engine import make_url
from sqlglot import exp
from tqdm import tqdm

from app.config import get_settings
from app.services.llm_factory import SUPPORTED_PROVIDERS, create_chat_model, default_model_for
from evaluation.bootstrap import EVAL_DIR
from evaluation.dataset import DEFAULT_DATASET, DIFFICULTIES, filter_examples, load_db_tables, load_examples
from evaluation.db import create_bird_engine, disable_schema_cache, execute_sql
from evaluation.report import write_report
from evaluation.runner import AgentEvaluator, RateLimitExhausted, RunOptions

RESULTS_DIR = EVAL_DIR / "results"
PREDICTIONS = "predictions.jsonl"

logger = logging.getLogger("evaluation")


def _bird_db_url() -> str:
    """BIRD_DB_URL, else the backend's DATABASE_URL pointed at the `bird` DB."""
    url = os.getenv("BIRD_DB_URL") or get_settings().DATABASE_URL
    if not url:
        raise SystemExit("Set BIRD_DB_URL (e.g. postgresql://postgres:<pw>@localhost:5432/bird)")
    if os.getenv("BIRD_DB_URL"):
        return url
    return make_url(url).set(database="bird").render_as_string(hide_password=False)


def _read_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _write_records(path: Path, records: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for r in sorted(records, key=lambda r: r["question_id"]):
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")


def _print_summary(summary: dict, run_dir: Path) -> None:
    total = summary["accuracy_by_difficulty"]["total"]
    print(
        f"\nScored {total['count']} questions | EX {total['ex']}% | "
        f"EX(col-tolerant) {total['ex_column_tolerant']}% | Soft-F1 {total['soft_f1']}%"
    )
    print(f"Status: {summary['status_counts']}")
    print(f"Report: {run_dir / 'report.md'}")


def _select_examples(args) -> list:
    return filter_examples(
        load_examples(Path(args.dataset)),
        db_ids=args.db_id,
        difficulties=args.difficulty,
        question_ids=args.question_id,
        sample=args.sample,
        seed=args.seed,
        limit=args.limit,
    )


# ── run ──────────────────────────────────────────────────────────────────────

def cmd_run(args) -> int:
    settings = get_settings()
    provider = (args.provider or settings.LLM_PROVIDER).lower()
    model = args.model or default_model_for(provider)
    run_name = args.run_name or (
        f"{provider}-{re.sub(r'[^A-Za-z0-9.-]+', '-', model)}-{datetime.now():%Y%m%d-%H%M%S}"
    )
    run_dir = RESULTS_DIR / run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    pred_path = run_dir / PREDICTIONS
    config_path = run_dir / "config.json"

    run_config = {
        "run_name": run_name,
        "provider": provider,
        "model": model,
        "dataset": Path(args.dataset).name,
        "use_evidence": not args.no_evidence,
        "full_schema": args.full_schema,
        "float_precision": args.float_precision,
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }
    if config_path.exists() and not args.fresh:
        previous = json.loads(config_path.read_text(encoding="utf-8"))
        for key in ("provider", "model", "use_evidence", "full_schema"):
            if previous.get(key) != run_config[key]:
                print(
                    f"Run '{run_name}' was started with {key}={previous.get(key)!r}, "
                    f"now {run_config[key]!r}. Use a new --run-name or --fresh.",
                    file=sys.stderr,
                )
                return 2
        run_config["started_at"] = previous.get("started_at", run_config["started_at"])
    if args.fresh and pred_path.exists():
        pred_path.unlink()
    config_path.write_text(json.dumps(run_config, indent=2), encoding="utf-8")

    examples = _select_examples(args)
    done = {r["question_id"] for r in _read_records(pred_path)}
    todo = [e for e in examples if e.question_id not in done]
    print(
        f"Run '{run_name}': {provider}/{model} | {len(examples)} selected, "
        f"{len(examples) - len(todo)} already done, {len(todo)} to go"
    )

    engine = create_bird_engine(_bird_db_url(), pool_size=max(2, args.workers * 2))
    disable_schema_cache()
    evaluator = AgentEvaluator(
        engine,
        create_chat_model(provider, model, max_retries=1),  # runner does its own backoff
        load_db_tables(),
        RunOptions(
            use_evidence=not args.no_evidence,
            full_schema=args.full_schema,
            rpm=args.rpm,
            exec_timeout_ms=args.timeout * 1000,
            float_precision=args.float_precision,
            max_output_rows=args.output_rows,
        ),
    )

    write_lock = threading.Lock()
    stop = threading.Event()
    correct = scored = 0
    aborted_reason = None

    def work(ex):
        if stop.is_set():
            return None
        return evaluator.evaluate(ex)

    with open(pred_path, "a", encoding="utf-8") as out, \
            ThreadPoolExecutor(max_workers=args.workers) as pool, \
            tqdm(total=len(todo), unit="q") as bar:
        pending = {pool.submit(work, ex): ex for ex in todo}
        try:
            while pending:
                finished, _ = wait(pending, return_when=FIRST_COMPLETED)
                for fut in finished:
                    ex = pending.pop(fut)
                    if fut.cancelled():
                        continue
                    try:
                        rec = fut.result()
                    except RateLimitExhausted as exc:
                        aborted_reason = aborted_reason or f"rate limit not recovering ({exc})"
                        stop.set()
                        continue
                    except Exception as exc:
                        logger.exception("q%s failed unexpectedly", ex.question_id)
                        aborted_reason = aborted_reason or f"unexpected error on q{ex.question_id}: {exc!r}"
                        stop.set()
                        continue
                    if rec is None:
                        continue
                    with write_lock:
                        out.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
                        out.flush()
                    scored += 1
                    correct += rec["status"] == "correct"
                    bar.update(1)
                    bar.set_postfix(EX=f"{100 * correct / scored:.1f}%")
                if stop.is_set():
                    for fut in pending:
                        fut.cancel()
        except KeyboardInterrupt:
            stop.set()
            for fut in pending:
                fut.cancel()
            aborted_reason = "interrupted"

    records = _read_records(pred_path)
    summary = write_report(run_dir, records, run_config)
    _print_summary(summary, run_dir)
    if aborted_reason:
        print(
            f"\nStopped early: {aborted_reason}\n"
            f"Resume with: python -m evaluation run --run-name {run_name} (same filters)",
            file=sys.stderr,
        )
        return 1
    return 0


# ── score ────────────────────────────────────────────────────────────────────

def cmd_score(args) -> int:
    run_dir = RESULTS_DIR / args.run_name
    pred_path = run_dir / PREDICTIONS
    records = _read_records(pred_path)
    if not records:
        print(f"No predictions found at {pred_path}", file=sys.stderr)
        return 2
    run_config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
    run_config["float_precision"] = args.float_precision

    evaluator = AgentEvaluator(
        create_bird_engine(_bird_db_url()),
        llm=None,
        db_tables=load_db_tables(),
        opts=RunOptions(
            exec_timeout_ms=args.timeout * 1000,
            float_precision=args.float_precision,
            max_output_rows=args.output_rows,
        ),
    )
    records = [evaluator.score(r) for r in tqdm(records, unit="q")]
    _write_records(pred_path, records)
    (run_dir / "config.json").write_text(json.dumps(run_config, indent=2), encoding="utf-8")
    _print_summary(write_report(run_dir, records, run_config), run_dir)
    return 0


# ── check-gold ───────────────────────────────────────────────────────────────

def cmd_check_gold(args) -> int:
    engine = create_bird_engine(_bird_db_url())
    db_tables = load_db_tables()
    mapped = {t for ts in db_tables.values() for t in ts}
    actual = set(inspect(engine).get_table_names())
    problems = 0

    if mapped != actual:
        problems += 1
        print(f"Table mapping mismatch. Missing in DB: {sorted(mapped - actual)}; "
              f"unmapped DB tables: {sorted(actual - mapped)}")
    else:
        print(f"Table mapping OK: {len(mapped)} tables across {len(db_tables)} databases")

    examples = _select_examples(args)
    empty = 0
    for ex in tqdm(examples, unit="q"):
        unknown_db = ex.db_id not in db_tables
        try:
            tree = sqlglot.parse_one(ex.gold_sql, read="postgres")
            ctes = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
            used = {t.name.lower() for t in tree.find_all(exp.Table)} - ctes
        except Exception:
            used = set()
        outside = used - set(db_tables.get(ex.db_id, []))
        res = execute_sql(engine, ex.gold_sql, timeout_ms=args.timeout * 1000)
        if unknown_db or outside or not res.ok:
            problems += 1
            detail = "unknown db_id" if unknown_db else (
                f"tables outside {ex.db_id}: {sorted(outside)}" if outside else res.error)
            tqdm.write(f"q{ex.question_id} [{ex.db_id}] {detail}")
        elif not res.rows:
            empty += 1
    print(f"Checked {len(examples)} gold queries: {problems} problem(s), "
          f"{empty} returned no rows (valid, but weak signal)")
    return 1 if problems else 0


# ── CLI ──────────────────────────────────────────────────────────────────────

def _add_selection_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--dataset", default=str(DEFAULT_DATASET), help="BIRD-format CSV")
    p.add_argument("--db-id", action="append", help="only this BIRD database (repeatable)")
    p.add_argument("--difficulty", action="append", choices=DIFFICULTIES, help="repeatable")
    p.add_argument("--question-id", action="append", type=int, help="repeatable")
    p.add_argument("--sample", type=int, help="stratified random sample of N questions")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--limit", type=int, help="first N questions after other filters")
    p.add_argument("--timeout", type=int, default=60, help="SQL execution timeout (seconds)")


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m evaluation", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="generate SQL with the agent and score it")
    _add_selection_args(run)
    run.add_argument("--provider", choices=SUPPORTED_PROVIDERS, help="default: LLM_PROVIDER")
    run.add_argument("--model", help="default: GEMINI_MODEL / GROQ_MODEL")
    run.add_argument("--run-name", help="results folder name; reuse it to resume")
    run.add_argument("--fresh", action="store_true", help="discard existing predictions for this run")
    run.add_argument("--workers", type=int, default=1, help="concurrent questions")
    run.add_argument("--rpm", type=float, help="max agent invocations per minute")
    run.add_argument("--no-evidence", action="store_true", help="omit BIRD evidence hints")
    run.add_argument("--full-schema", action="store_true",
                     help="give the agent all 75 BIRD tables instead of the question's database")
    run.add_argument("--float-precision", type=int, default=4)
    run.add_argument("--output-rows", type=int, default=100,
                     help="rows of gold/pred output stored per question (0 = all)")
    run.set_defaults(func=cmd_run)

    score = sub.add_parser("score", help="re-score an existing run (no LLM calls)")
    score.add_argument("--run-name", required=True)
    score.add_argument("--timeout", type=int, default=60)
    score.add_argument("--float-precision", type=int, default=4)
    score.add_argument("--output-rows", type=int, default=100,
                       help="rows of gold/pred output stored per question (0 = all)")
    score.set_defaults(func=cmd_score)

    check = sub.add_parser("check-gold", help="validate dataset, table mapping and gold SQL")
    _add_selection_args(check)
    check.set_defaults(func=cmd_check_gold)

    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
