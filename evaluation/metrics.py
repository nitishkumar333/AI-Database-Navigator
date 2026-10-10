"""
Result-comparison metrics.

- execution_accuracy: BIRD's official EX, i.e. set(pred_rows) == set(gold_rows).
  Row order and duplicates are ignored; column order and count matter.
- soft_f1: BIRD mini-dev's Soft-F1, a partial-credit score that compares
  values per row and tolerates extra or missing columns.
- column_tolerant_match: our addition. Passes when some projection of the
  predicted columns (any order) gives exactly the gold row set. It tolerates
  the extra columns the production prompt asks for (image URLs, helper
  aliases), which strict EX would count as wrong.

All metrics run on normalized values, so Postgres type differences don't
count as mismatches. For example, NUMERIC 0.5 and REAL 0.5 compare equal.
"""
import itertools
import json
import math
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Iterable

_MAX_PROJECTIONS = 5_000


def normalize_value(value: Any, float_precision: int = 4) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, (float, Decimal)):
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return str(f)
        rounded = round(f, float_precision)
        return int(rounded) if rounded.is_integer() else rounded
    if isinstance(value, (datetime, date, time, timedelta)):
        return value
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value)
    if isinstance(value, (list, tuple, dict)):
        return json.dumps(value, sort_keys=True, default=str)
    return str(value)


def normalize_rows(rows: Iterable[Iterable[Any]], float_precision: int = 4) -> list[tuple]:
    return [tuple(normalize_value(v, float_precision) for v in row) for row in rows]


def execution_accuracy(pred: list[tuple], gold: list[tuple]) -> bool:
    return set(pred) == set(gold)


def _row_match(pred_row: tuple, gold_row: tuple) -> tuple[float, float, float]:
    total = len(gold_row) or 1
    matches = sum(1 for v in pred_row if v in gold_row)
    pred_only = len(pred_row) - matches
    truth_only = sum(1 for v in gold_row if v not in pred_row)
    return matches / total, pred_only / total, truth_only / total


def soft_f1(pred: list[tuple], gold: list[tuple]) -> float:
    """Port of calculate_f1_score from bird-bench/mini_dev evaluation_f1.py
    (rows de-duplicated in order, then paired positionally)."""
    if not pred and not gold:
        return 1.0
    pred = list(dict.fromkeys(pred))
    gold = list(dict.fromkeys(gold))

    tp = fp = fn = 0.0
    for i, gold_row in enumerate(gold):
        if i >= len(pred):
            fn += 1
            continue
        m, p, t = _row_match(pred[i], gold_row)
        tp, fp, fn = tp + m, fp + p, fn + t
    fp += max(0, len(pred) - len(gold))

    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def column_tolerant_match(pred: list[tuple], gold: list[tuple]) -> bool:
    if execution_accuracy(pred, gold):
        return True
    if not pred or not gold:
        return False

    gold_set = set(gold)
    gold_width, pred_width = len(gold[0]), len(pred[0])
    if pred_width < gold_width:
        return False

    gold_cols = [{r[j] for r in gold} for j in range(gold_width)]
    pred_cols = [{r[k] for r in pred} for k in range(pred_width)]
    candidates = [
        [k for k in range(pred_width) if pred_cols[k] == gold_cols[j]]
        for j in range(gold_width)
    ]
    if any(not c for c in candidates):
        return False

    for combo in itertools.islice(itertools.product(*candidates), _MAX_PROJECTIONS):
        if len(set(combo)) != len(combo):
            continue
        if {tuple(r[k] for k in combo) for r in pred} == gold_set:
            return True
    return False


def score(pred_rows, gold_rows, float_precision: int = 4) -> dict:
    pred = normalize_rows(pred_rows, float_precision)
    gold = normalize_rows(gold_rows, float_precision)
    return {
        "ex": execution_accuracy(pred, gold),
        "ex_column_tolerant": column_tolerant_match(pred, gold),
        "soft_f1": round(soft_f1(pred, gold), 6),
    }
