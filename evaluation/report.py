"""Aggregates scored prediction records into summary.json and report.md."""
import json
import math
import statistics
from collections import Counter
from pathlib import Path

from evaluation.dataset import DIFFICULTIES
from evaluation.linking import failure_category

_METRICS = (
    ("ex", "EX (BIRD official)"),
    ("ex_column_tolerant", "EX (column-tolerant)"),
    ("soft_f1", "Soft-F1"),
)

_LINKING = (
    ("context_recall", "Gold tables present in agent context"),
    ("table_recall", "Table recall (pred SQL vs gold)"),
    ("table_precision", "Table precision"),
    ("tables_exact", "Exact table set"),
    ("column_recall", "Column recall"),
    ("column_precision", "Column precision"),
)


def wilson_ci(successes: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """95% Wilson score interval, in percent. Tells you how far apart two
    runs must be before the difference means anything."""
    if not n:
        return None
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return round(100 * (centre - half), 2), round(100 * (centre + half), 2)


def _scorable(records: list[dict]) -> list[dict]:
    return [r for r in records if r.get("status") != "gold_error"]


def _bucket(records: list[dict]) -> dict:
    scorable = _scorable(records)
    n = len(scorable)
    out = {"count": n}
    for key, _ in _METRICS:
        values = [float(r["metrics"][key]) for r in scorable]
        out[key] = round(100 * sum(values) / n, 2) if n else None
    out["ex_ci95"] = wilson_ci(sum(bool(r["metrics"]["ex"]) for r in scorable), n)
    return out


def _mean_pct(values) -> float | None:
    values = [float(v) for v in values if v is not None]
    return round(100 * sum(values) / len(values), 2) if values else None


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    return round(values[min(len(values) - 1, int(pct * len(values)))], 3)


def _tool_call_total(rec: dict) -> int:
    calls = rec.get("tool_calls")
    if calls:
        return sum(calls.values())
    # Records from before tool_calls was traced only have the SQL attempts.
    return len(rec.get("attempted_sql") or [])


def _linking(records: list[dict]) -> dict:
    scorable = _scorable(records)
    links = [r.get("linking") or {} for r in scorable]
    out = {key: _mean_pct(link.get(key) for link in links) for key, _ in _LINKING}
    out["questions_with_pred_sql"] = sum(1 for link in links if link.get("pred_tables") is not None)
    exact = [r for r, link in zip(scorable, links) if link.get("tables_exact") is True]
    wrong = [r for r, link in zip(scorable, links) if link.get("tables_exact") is False]
    out["ex_when_tables_exact"] = {"count": len(exact), "ex": _bucket(exact)["ex"]}
    out["ex_when_tables_wrong"] = {"count": len(wrong), "ex": _bucket(wrong)["ex"]}
    return out


def _behaviour(records: list[dict]) -> dict:
    n = len(records)
    if not n:
        return {"count": 0}
    usage = [r.get("usage") or {} for r in records]
    latencies = [r["latency_s"] for r in records if r.get("latency_s") is not None]
    return {
        "count": n,
        "avg_tokens": round(sum(u.get("total_tokens", 0) for u in usage) / n, 1),
        "avg_llm_calls": round(sum(r.get("llm_calls", 0) for r in records) / n, 2),
        "avg_tool_calls": round(sum(_tool_call_total(r) for r in records) / n, 2),
        "latency_p50": _percentile(latencies, 0.5),
        "latency_p95": _percentile(latencies, 0.95),
    }


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
    tool_usage = Counter()
    for r in records:
        tool_usage.update(r.get("tool_calls") or {})

    behaviour = {d: _behaviour([r for r in records if r["difficulty"] == d]) for d in DIFFICULTIES}
    behaviour["total"] = _behaviour(records)

    return {
        "run": run_config,
        "questions": len(records),
        "accuracy_by_difficulty": by_difficulty,
        "accuracy_by_db": by_db,
        "status_counts": dict(Counter(r.get("status", "unscored") for r in records).most_common()),
        "failure_categories": dict(Counter(
            c for c in (failure_category(r) for r in records) if c
        ).most_common()),
        "schema_linking": _linking(records),
        "cost": {
            "input_tokens": sum(u.get("input_tokens", 0) for u in usage),
            "output_tokens": sum(u.get("output_tokens", 0) for u in usage),
            "avg_tokens_per_question": round(sum(u.get("total_tokens", 0) for u in usage) / n, 1),
            "avg_llm_calls_per_question": round(sum(r.get("llm_calls", 0) for r in records) / n, 2),
        },
        "behaviour_by_difficulty": behaviour,
        "tool_usage": dict(tool_usage.most_common()),
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


def schema_label(run: dict) -> str:
    """Runs from before the key existed used the basic format."""
    label = run.get("schema_format", "basic")
    return label + (" + descriptions" if run.get("describe") else "")


def _fmt_ci(ci) -> str:
    return "-" if not ci else f"{ci[0]:.1f}-{ci[1]:.1f}"


def render_markdown(summary: dict) -> str:
    run = summary["run"]
    diff = summary["accuracy_by_difficulty"]
    cols = [*DIFFICULTIES, "total"]
    lines = [
        f"# SQL Agent Evaluation: `{run.get('run_name')}`",
        "",
        f"- **Provider / model:** {run.get('provider')} / `{run.get('model')}`",
        f"- **Dataset:** {run.get('dataset')} ({summary['questions']} questions scored)"
        + (f" | **Split:** `{run['split']}`" if run.get("split") else ""),
        f"- **Evidence hints:** {'on' if run.get('use_evidence') else 'off'}  "
        f"| **Schema scope:** {'all BIRD tables' if run.get('full_schema') else 'per-database'}  "
        f"| **Schema format:** {schema_label(run)}",
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
    lines.append("| EX 95% CI | " + " | ".join(_fmt_ci(diff[c].get("ex_ci95")) for c in cols) + " |")
    lines += [
        "",
        "Two runs whose EX confidence intervals overlap heavily are not reliably different; "
        "use `python -m evaluation compare` for a paired test on the same questions.",
    ]

    lines += ["", "## By database", "", "| db_id | n | EX | EX (col-tolerant) | Soft-F1 |", "|---|---:|---:|---:|---:|"]
    for db, b in summary["accuracy_by_db"].items():
        lines.append(f"| {db} | {b['count']} | {_fmt(b['ex'])} | {_fmt(b['ex_column_tolerant'])} | {_fmt(b['soft_f1'])} |")

    lines += ["", "## Outcome breakdown", "", "| Status | Count |", "|---|---:|"]
    lines += [f"| {k} | {v} |" for k, v in summary["status_counts"].items()]

    if summary.get("failure_categories"):
        lines += [
            "", "## Why questions were missed", "",
            "Heuristic first-cause per missed question (see `evaluation/linking.py`).",
            "", "| Category | Count |", "|---|---:|",
        ]
        lines += [f"| {k} | {v} |" for k, v in summary["failure_categories"].items()]

    link = summary.get("schema_linking")
    if link:
        lines += [
            "", "## Schema linking (%)", "",
            f"Tables/columns referenced by the predicted SQL vs the gold SQL "
            f"({link['questions_with_pred_sql']} questions with a prediction).",
            "", "| Metric | Value |", "|---|---:|",
        ]
        lines += [f"| {label} | {_fmt(link.get(key))} |" for key, label in _LINKING]
        ex_ok, ex_bad = link["ex_when_tables_exact"], link["ex_when_tables_wrong"]
        lines += [
            f"| EX when table set is exact (n={ex_ok['count']}) | {_fmt(ex_ok['ex'])} |",
            f"| EX when table set is wrong (n={ex_bad['count']}) | {_fmt(ex_bad['ex'])} |",
        ]

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
    ]
    if summary.get("tool_usage"):
        lines.append("- Tool calls: " + ", ".join(
            f"`{name}` {count}" for name, count in summary["tool_usage"].items()))

    behaviour = summary.get("behaviour_by_difficulty")
    if behaviour:
        lines += [
            "", "| | " + " | ".join(cols) + " |", "|---|" + "---:|" * len(cols),
        ]
        for key, label in (("avg_tokens", "Avg tokens"), ("avg_llm_calls", "Avg LLM calls"),
                           ("avg_tool_calls", "Avg tool calls"), ("latency_p50", "Latency p50 (s)"),
                           ("latency_p95", "Latency p95 (s)")):
            values = (behaviour[c].get(key) for c in cols)
            lines.append(f"| {label} | " + " | ".join(
                "-" if v is None else str(v) for v in values) + " |")

    lines += [
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
