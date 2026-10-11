"""Loading and filtering the BIRD mini-dev (PostgreSQL) dataset."""
import csv
import json
import random
from dataclasses import dataclass
from pathlib import Path

from evaluation.bootstrap import EVAL_DIR

DEFAULT_DATASET = EVAL_DIR / "data" / "bird_minidev_postgresql.csv"
DB_TABLES_FILE = EVAL_DIR / "data" / "bird_db_tables.json"
SPLITS_DIR = EVAL_DIR / "data" / "splits"
DIFFICULTIES = ("simple", "moderate", "challenging")


@dataclass(frozen=True)
class Example:
    question_id: int
    db_id: str
    question: str
    evidence: str
    gold_sql: str
    difficulty: str

    def prompt(self, use_evidence: bool) -> str:
        """The user message sent to the agent.

        BIRD's standard setting supplies the external-knowledge "evidence";
        production users don't, so it is switchable.
        """
        if use_evidence and self.evidence:
            return f"{self.question}\n\nHint: {self.evidence}"
        return self.question


def load_examples(path: Path = DEFAULT_DATASET) -> list[Example]:
    # utf-8-sig: the exported CSV starts with a BOM.
    with open(path, newline="", encoding="utf-8-sig") as f:
        return [
            Example(
                question_id=int(row["question_id"]),
                db_id=row["db_id"].strip(),
                question=row["question"].strip(),
                evidence=(row.get("evidence") or "").strip(),
                gold_sql=row["SQL"].strip(),
                difficulty=row["difficulty"].strip().lower(),
            )
            for row in csv.DictReader(f)
        ]


def filter_examples(
    examples: list[Example],
    *,
    db_ids: list[str] | None = None,
    difficulties: list[str] | None = None,
    question_ids: list[int] | None = None,
    split_ids: list[int] | None = None,
    sample: int | None = None,
    seed: int = 42,
    limit: int | None = None,
) -> list[Example]:
    if db_ids:
        examples = [e for e in examples if e.db_id in set(db_ids)]
    if difficulties:
        examples = [e for e in examples if e.difficulty in set(difficulties)]
    if question_ids:
        examples = [e for e in examples if e.question_id in set(question_ids)]
    if split_ids is not None:
        examples = [e for e in examples if e.question_id in set(split_ids)]
    if sample is not None and sample < len(examples):
        # Stratified by difficulty so a small sample keeps BIRD's mix.
        rng = random.Random(seed)
        by_diff: dict[str, list[Example]] = {}
        for e in examples:
            by_diff.setdefault(e.difficulty, []).append(e)
        picked: list[Example] = []
        for group in by_diff.values():
            k = round(sample * len(group) / len(examples))
            picked.extend(rng.sample(group, min(k, len(group))))
        rest = [e for e in examples if e not in set(picked)]
        rng.shuffle(rest)
        picked.extend(rest[: max(0, sample - len(picked))])
        picked = picked[:sample]
        examples = sorted(picked, key=lambda e: e.question_id)
    if limit is not None:
        examples = examples[:limit]
    return examples


def load_db_tables() -> dict[str, list[str]]:
    """BIRD db_id -> tables. All BIRD databases live in one Postgres schema,
    so this plays the role a knowledge base plays in production."""
    with open(DB_TABLES_FILE, encoding="utf-8") as f:
        return json.load(f)


# ── Frozen splits ────────────────────────────────────────────────────────────
#
# A split is a committed list of question ids. Unlike --sample, it never
# changes when the dataset file, the filters or the Python version change, so
# runs made weeks apart are scored on exactly the same questions.

def make_split(examples: list[Example], size: int, seed: int = 42) -> list[int]:
    """Question ids stratified by (db_id, difficulty).

    Each stratum gets its proportional share, rounded with the largest-remainder
    method so the total is exactly `size` and every database keeps its weight.
    """
    if not 0 < size <= len(examples):
        raise ValueError(f"size must be between 1 and {len(examples)}")
    rng = random.Random(seed)
    strata: dict[tuple[str, str], list[Example]] = {}
    for e in sorted(examples, key=lambda e: e.question_id):
        strata.setdefault((e.db_id, e.difficulty), []).append(e)
    keys = sorted(strata)
    quotas = {k: size * len(strata[k]) / len(examples) for k in keys}
    alloc = {k: int(q) for k, q in quotas.items()}
    tie_break = {k: rng.random() for k in keys}
    by_remainder = sorted(keys, key=lambda k: (alloc[k] - quotas[k], tie_break[k]))
    for k in by_remainder[: size - sum(alloc.values())]:
        alloc[k] += 1
    return sorted(e.question_id for k in keys for e in rng.sample(strata[k], alloc[k]))


def split_path(name_or_path: str) -> Path:
    path = Path(name_or_path)
    if path.suffix == ".json" and path.exists():
        return path
    return SPLITS_DIR / f"{name_or_path}.json"


def load_split(name_or_path: str) -> dict:
    path = split_path(name_or_path)
    if not path.exists():
        available = sorted(p.stem for p in SPLITS_DIR.glob("*.json"))
        raise SystemExit(f"Unknown split '{name_or_path}'. Available: {available}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)
