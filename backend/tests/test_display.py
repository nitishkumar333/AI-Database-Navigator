import datetime as dt
import json
from decimal import Decimal

import pytest

from app.services.display import (
    DisplayHint, build_views, describe_columns, describe_result, json_rows, trim_rows,
    upgrade_stored,
)

PRODUCTS = [
    {"id": i, "name": f"Item {i}", "price": Decimal("9.50") + i,
     "image_url": f"https://images.unsplash.com/photo-{i}?w=400"}
    for i in range(1, 6)
]
MONTHLY = [
    {"month": dt.date(2024, m, 1), "revenue": Decimal(1000 * m), "orders": 10 * m}
    for m in range(1, 7)
]


def _views(rows, hint=None, truncated=False):
    columns = list(rows[0]) if rows else []
    result = describe_result(columns, rows, truncated=truncated, hint=hint)
    return result["views"], result["display_note"]


# ── Column types and roles ───────────────────────────────────────────────────

def test_column_types_and_roles():
    meta = {c["name"]: c for c in describe_columns(list(PRODUCTS[0]), PRODUCTS)}
    assert meta["id"] == {"name": "id", "type": "number", "role": "id"}
    assert meta["price"]["type"] == "number"
    assert meta["name"] == {"name": "name", "type": "text", "role": None}
    assert meta["image_url"]["role"] == "image"


def test_extensionless_image_url_is_found_by_column_name():
    rows = [{"title": "a", "thumbnail": "https://cdn.example.com/img/123"}]
    meta = describe_columns(["title", "thumbnail"], rows)
    assert meta[1]["role"] == "image"


def test_plain_link_is_a_url_not_an_image():
    rows = [{"name": "a", "homepage": "https://example.com/about"}]
    assert describe_columns(["name", "homepage"], rows)[1]["role"] == "url"


def test_loose_names_are_not_misread():
    # The old frontend heuristic read 'location' as a category and
    # 'total_amount' as a price; nothing here is an image, so no cards.
    rows = [{"location": "Paris", "total_amount": 5, "avatar": None}]
    views, _ = _views(rows)
    assert views[0]["type"] != "cards"


def test_iso_strings_are_dates():
    rows = [{"d": "2024-01-01", "t": "2024-01-01T10:00:00+00:00"}]
    meta = describe_columns(["d", "t"], rows)
    assert [c["type"] for c in meta] == ["date", "datetime"]


def test_duplicate_column_names_are_described_once():
    assert len(describe_columns(["a", "a"], [{"a": 1}])) == 1


# ── Default views ────────────────────────────────────────────────────────────

def test_records_with_images_default_to_cards_keeping_every_column():
    views, note = _views(PRODUCTS)
    assert note == ""
    cards = views[0]
    assert cards == {"type": "cards", "image": "image_url", "title": "name",
                     "fields": ["id", "price"]}
    assert {"type": "table"} in views


def test_single_row_is_a_stat():
    views, _ = _views([{"total": 42, "average": Decimal("3.5")}])
    assert views[0] == {"type": "stat", "fields": ["total", "average"]}


def test_auto_never_picks_a_chart_but_offers_one():
    views, _ = _views(MONTHLY)
    assert views[0] == {"type": "table"}
    assert views[1] == {"type": "line", "x": "month", "y": ["revenue", "orders"], "series": None}


def test_empty_result_is_a_table():
    assert build_views([], [], hint=DisplayHint(type="bar"))[0][0] == {"type": "table"}


# ── Hints ────────────────────────────────────────────────────────────────────

def test_valid_chart_hint_is_used():
    views, note = _views(MONTHLY, DisplayHint.parse("line", "month", ["revenue"]))
    assert views[0] == {"type": "line", "x": "month", "y": ["revenue"], "series": None}
    assert note == "Display: shown as a line chart."


def test_hint_columns_are_matched_loosely():
    views, _ = _views(MONTHLY, DisplayHint.parse("bar", 'o."Month"', "REVENUE"))
    assert views[0]["x"] == "month" and views[0]["y"] == ["revenue"]


def test_missing_roles_are_filled_in():
    views, _ = _views(MONTHLY, DisplayHint.parse("bar"))
    assert views[0] == {"type": "bar", "x": "month", "y": ["revenue", "orders"], "series": None}


def test_chart_of_truncated_result_falls_back():
    views, note = _views(MONTHLY, DisplayHint.parse("line"), truncated=True)
    assert views[0]["type"] == "table"
    assert "more rows than were fetched" in note


@pytest.mark.parametrize("hint, reason", [
    (DisplayHint.parse("bar", "month", ["nope"]), "'nope' is not in the result"),
    (DisplayHint.parse("line", "revenue", ["month"]), "'month' is not numeric"),
    (DisplayHint.parse("scatter", "month", ["revenue"]), "'month' is not numeric"),
])
def test_unfit_hints_fall_back_with_a_reason(hint, reason):
    views, note = _views(MONTHLY, hint)
    assert views[0]["type"] == "table"
    assert reason in note


def test_pie_limits():
    slices = [{"segment": f"s{i}", "share": i + 1} for i in range(12)]
    _, note = _views(slices, DisplayHint.parse("pie"))
    assert "2 to 8" in note
    views, _ = _views(slices[:4], DisplayHint.parse("pie"))
    assert views[0] == {"type": "pie", "x": "segment", "y": ["share"], "series": None}
    _, note = _views([{"k": "a", "v": -1}, {"k": "b", "v": 2}], DisplayHint.parse("pie"))
    assert "positive" in note


def test_series_chart():
    rows = [{"month": f"2024-0{m}", "region": r, "sales": m * 10}
            for m in range(1, 4) for r in ("north", "south")]
    views, _ = _views(rows, DisplayHint.parse("line", "month", ["sales"], "region"))
    assert views[0] == {"type": "line", "x": "month", "y": ["sales"], "series": "region"}


def test_too_many_bar_categories():
    rows = [{"name": f"n{i}", "v": i} for i in range(60)]
    _, note = _views(rows, DisplayHint.parse("bar"))
    assert "at most 50" in note


def test_cards_hint_without_image_falls_back():
    views, note = _views(MONTHLY, DisplayHint.parse("cards"))
    assert views[0]["type"] == "table"
    assert "no image column" in note


def test_unknown_hint_type_is_auto():
    assert DisplayHint.parse("heatmap").type == "auto"


# ── JSON and stored answers ──────────────────────────────────────────────────

def test_json_rows_keep_numbers_numeric():
    rows = json_rows([{"a": Decimal("2.50"), "b": Decimal("3"), "c": dt.date(2024, 1, 2),
                       "d": float("nan"), "e": b"\x00\x01"}])
    assert rows == [{"a": 2.5, "b": 3, "c": "2024-01-02", "d": None, "e": "\\x0001"}]
    json.dumps(rows)


def test_stored_answer_without_views_is_upgraded():
    stored = {"columns": list(PRODUCTS[0]), "rows": json_rows(PRODUCTS), "success": True}
    upgraded = upgrade_stored(stored)
    assert upgraded["views"][0]["type"] == "cards"
    assert upgraded["column_meta"][0]["name"] == "id"
    assert upgrade_stored(upgraded) is upgraded


def test_full_legacy_answer_offers_no_chart():
    rows = [{"name": f"n{i}", "v": i} for i in range(50)]
    upgraded = upgrade_stored({"columns": ["name", "v"], "rows": rows})
    assert [v["type"] for v in upgraded["views"]] == ["table"]
    rows = rows[:10]
    upgraded = upgrade_stored({"columns": ["name", "v"], "rows": rows})
    assert [v["type"] for v in upgraded["views"]] == ["table", "bar"]


# ── Trimmed cells ────────────────────────────────────────────────────────────

def test_trim_rules():
    words = "word " * 100                        # 500 chars with spaces
    token = "a" * 150                            # no whitespace, not a link
    link = "https://cdn.example.com/" + "p" * 900                # 924 chars: kept
    long_link = "https://cdn.example.com/" + "q" * 1200
    bcrypt = "$2b$12$" + "x" * 53
    rows, cut = trim_rows([{
        "notes": words, "sha": token, "image_url": link, "signed": long_link,
        "password_hash": "y" * 60, "secret_col": bcrypt, "short": "ok", "n": 5,
        "blob": b"\x00" * 80, "doc": {"k": "v" * 400},
    }])
    row = rows[0]
    assert row["notes"] == words[:300] + "..."
    assert row["sha"] == "a" * 100 + "..."
    assert row["image_url"] == link
    assert row["signed"] == long_link[:1000] + "..."
    assert row["password_hash"] == "y" * 20 + "..."
    assert row["secret_col"] == bcrypt[:20] + "..."        # hash format, any column name
    assert row["short"] == "ok" and row["n"] == 5
    assert row["blob"].endswith("...") and len(row["blob"]) == 103
    assert row["doc"].endswith("...") and len(row["doc"]) == 303
    assert cut == ["notes", "sha", "signed", "password_hash", "secret_col", "blob", "doc"]


def test_trim_keeps_values_at_the_limit():
    rows, cut = trim_rows([{"t": "a b" * 100, "h": "a" * 100, "j": {"k": 1}}])
    assert rows[0] == {"t": "a b" * 100, "h": "a" * 100, "j": {"k": 1}}
    assert cut == []
