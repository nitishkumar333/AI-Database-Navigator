"""
Side-by-side comparison of evaluation runs on the questions they share.

The first run is the baseline. For every other run the comparison is paired:
questions it fixed and broke relative to the baseline, plus an exact McNemar
p-value. That is the right test for "did this change help?" because both runs
answer the same questions, and it needs far fewer questions than comparing
two independent accuracy numbers.
"""
import math
from collections import Counter

from evaluation.linking import failure_category
from evaluation.report import schema_label, summarize

_MAX_LISTED_IDS = 25


def mcnemar_p(fixed: int, broken: int) -> float:
    """Exact two-sided McNemar test on the discordant pairs."""
    n = fixed + broken
    if not n:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(fixed, broken) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def _fmt(v, suffix: str = "") -> str:
    return "-" if v is None else f"{v}{suffix}"


def _ids(ids: list[int]) -> str:
    shown = ", ".join(str(i) for i in ids[:_MAX_LISTED_IDS])
    return shown + (f" … (+{len(ids) - _MAX_LISTED_IDS})" if len(ids) > _MAX_LISTED_IDS else "")


def compare_runs(runs: list[tuple[str, list[dict], dict]]) -> str:
    """runs: (run_name, scored records, run config). Returns markdown."""
    common = set.intersection(*(
        {r["question_id"] for r in records if r.get("status") not in (None, "gold_error")}
        for _, records, _ in runs
    ))
    if not common:
        return "No scorable questions are shared by all runs.\n"

    subsets = [
        (name, [r for r in records if r["question_id"] in common], config)
        for name, records, config in runs
    ]
    summaries = [summarize(records, config) for _, records, config in subsets]

    lines = [
        "# Run comparison",
        "",
        f"Compared on the **{len(common)} questions** scored in every run "
        f"(baseline: `{runs[0][0]}`).",
        "",
        "| Run | Model | Evidence | Schema | Split | Accuracy | 95% CI | EX strict | Soft-F1 "
        "| Tables exact | Col. recall | Avg tokens | Avg LLM calls | Avg tool calls | p50 s |",
        "|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for (name, _, config), s in zip(subsets, summaries):
        total = s["accuracy_by_difficulty"]["total"]
        link = s["schema_linking"]
        beh = s["behaviour_by_difficulty"]["total"]
        ci = total.get("accuracy_ci95")
        lines.append(
            f"| `{name}` | `{config.get('model')}` | {'on' if config.get('use_evidence') else 'off'} "
            f"| {schema_label(config)} | {config.get('split') or '-'} | {_fmt(total['accuracy'])} "
            f"| {f'{ci[0]:.1f}-{ci[1]:.1f}' if ci else '-'} | {_fmt(total['ex'])} "
            f"| {_fmt(total['soft_f1'])} | {_fmt(link['tables_exact'])} | {_fmt(link['column_recall'])} "
            f"| {_fmt(beh.get('avg_tokens'))} | {_fmt(beh.get('avg_llm_calls'))} "
            f"| {_fmt(beh.get('avg_tool_calls'))} | {_fmt(beh.get('latency_p50'))} |"
        )

    lines += ["", "## Accuracy by difficulty", "", "| Run | simple | moderate | challenging |", "|---|---:|---:|---:|"]
    for (name, _, _), s in zip(subsets, summaries):
        d = s["accuracy_by_difficulty"]
        lines.append(f"| `{name}` | " + " | ".join(
            f"{_fmt(d[k]['accuracy'])} (n={d[k]['count']})" for k in ("simple", "moderate", "challenging")
        ) + " |")

    base_name, base_records, _ = subsets[0]
    base_ok = {r["question_id"] for r in base_records if r["status"] == "correct"}
    if len(subsets) > 1:
        lines += [
            "", f"## Paired vs `{base_name}`", "",
            "| Run | Fixed | Broken | Net | McNemar p |", "|---|---:|---:|---:|---:|",
        ]
        details = []
        for name, records, _ in subsets[1:]:
            ok = {r["question_id"] for r in records if r["status"] == "correct"}
            fixed, broken = sorted(ok - base_ok), sorted(base_ok - ok)
            p = mcnemar_p(len(fixed), len(broken))
            lines.append(f"| `{name}` | {len(fixed)} | {len(broken)} | "
                         f"{len(fixed) - len(broken):+d} | {p:.3f} |")
            details += [f"- `{name}` fixed: {_ids(fixed) or '-'}",
                        f"- `{name}` broke: {_ids(broken) or '-'}"]
        lines += ["", "p < 0.05 means the difference is unlikely to be noise.", "", *details]

    counts = [Counter(c for c in (failure_category(r) for r in records) if c)
              for _, records, _ in subsets]
    categories = sorted(set().union(*counts), key=lambda c: -sum(cnt[c] for cnt in counts))
    if categories:
        lines += ["", "## Why questions were missed", "",
                  "| Category | " + " | ".join(f"`{n}`" for n, _, _ in subsets) + " |",
                  "|---|" + "---:|" * len(subsets)]
        lines += [f"| {c} | " + " | ".join(str(cnt[c]) for cnt in counts) + " |" for c in categories]

    return "\n".join(lines) + "\n"
