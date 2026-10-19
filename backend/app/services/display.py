"""
How a query result is displayed.

The backend decides and the frontend only renders. For each answer:

  describe_columns()  types every result column from its values (number,
                      date, text, ...) and marks its role: an image URL,
                      another URL, or an id.
  build_views()       turns the agent's display hint (submit_answer's
                      `display`, `x`, `y`, `series`) into view specs that are
                      checked against the result: the columns exist, the
                      chart's measures are numeric, the result is complete and
                      small enough to chart. A hint that doesn't fit falls
                      back to a view that does, and the reason is returned so
                      the agent's reply can say so.

Views, in order (the first is the default; the others are offered as
alternatives the user can switch to):
  {"type": "table"}
  {"type": "stat",  "fields": [col, ...]}
  {"type": "cards", "image": col, "title": col | None, "fields": [col, ...]}
  {"type": "bar" | "line" | "pie" | "scatter", "x": col, "y": [col, ...],
   "series": col | None}

json_rows() makes result rows JSON-safe the same way for the API response and
for the stored conversation, so a reloaded answer renders like the live one.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import re
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable

TABLE, STAT, CARDS = "table", "stat", "cards"
BAR, LINE, PIE, SCATTER = "bar", "line", "pie", "scatter"
CHARTS = (BAR, LINE, PIE, SCATTER)
VIEW_TYPES = (TABLE, STAT, CARDS) + CHARTS
AUTO = "auto"

# Column types and roles.
NUMBER, DATE, DATETIME, BOOLEAN, TEXT, JSON, OTHER = (
    "number", "date", "datetime", "boolean", "text", "json", "other")
IMAGE, URL, ID = "image", "url", "id"

MAX_STAT_FIELDS = 6
MAX_BAR_CATEGORIES = 50
# Charts use an 8-hue categorical palette (no generated 9th colour); a scatter's
# overlapping points only stay distinguishable with 3.
MAX_PIE_SLICES = 8
MAX_SERIES = 8
MAX_SCATTER_SERIES = 3
MAX_MEASURES = 6
MIN_LINE_POINTS = 2
MIN_SCATTER_POINTS = 3
URL_SHARE = 0.8          # share of a column's values that must be URLs
_LEGACY_STORED_ROWS = 50

_LABELS = {TABLE: "table", STAT: "summary", CARDS: "cards", BAR: "bar chart",
           LINE: "line chart", PIE: "pie chart", SCATTER: "scatter plot"}

_URL = re.compile(r"^https?://[^\s]+$", re.IGNORECASE)
_IMAGE_EXTENSION = re.compile(r"\.(jpe?g|png|gif|webp|avif|svg|bmp|ico)([?#]|$)", re.IGNORECASE)
_IMAGE_NAME = re.compile(
    r"image|img|photo|picture|thumb|avatar|logo|icon|poster|banner|cover", re.IGNORECASE)
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ISO_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?$")
_TITLE_NAMES = ("name", "title", "label")


# ──────────────────────────────────────────────────────────────────────────────
# JSON-safe rows
# ──────────────────────────────────────────────────────────────────────────────

def json_value(value: Any) -> Any:
    """A JSON-safe copy of one database value. Numbers stay numbers (Decimal
    is not turned into a string), dates become ISO strings."""
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Decimal):
        if not value.is_finite():
            return None
        return int(value) if value == value.to_integral_value() and abs(value) < 2**53 else float(value)
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, dt.timedelta):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        data = bytes(value)
        return "\\x" + data[:64].hex() + ("…" if len(data) > 64 else "")
    if isinstance(value, dict):
        return {str(k): json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_value(v) for v in value]
    return str(value)


def json_rows(rows: Iterable[dict]) -> list[dict]:
    return [{k: json_value(v) for k, v in row.items()} for row in rows or []]


# ──────────────────────────────────────────────────────────────────────────────
# Trimmed cells (what the agent sees and what the client gets)
# ──────────────────────────────────────────────────────────────────────────────

TRIM_MARK = "..."
TEXT_LIMIT = 300        # any other value
LINK_LIMIT = 500       # a link without whitespace (signed URLs run long)
TOKEN_LIMIT = 50       # a value without whitespace that isn't a link (hashes, base64, keys)
PASSWORD_LIMIT = 20     # password hashes

_PASSWORD_NAME = re.compile(r"pass(word|wd)?|pwd", re.IGNORECASE)
_PASSWORD_VALUE = re.compile(r"^\$(2[abxy]?|argon2(id|i|d)?|pbkdf2[\w-]*|scrypt|[156])\$")
_LINK = re.compile(r"^https?://", re.IGNORECASE)


def _trim_value(column: str, value: Any) -> tuple[Any, bool]:
    if isinstance(value, (bytes, bytearray, memoryview)):
        value = "\\x" + bytes(value).hex()
    elif isinstance(value, (dict, list, tuple)):
        text = json.dumps(value, default=str, ensure_ascii=False)
        if len(text) <= TEXT_LIMIT:
            return value, False
        value = text
    if not isinstance(value, str):
        return value, False
    unbroken = not any(ch.isspace() for ch in value)
    if _PASSWORD_NAME.search(column) or _PASSWORD_VALUE.match(value):
        limit = PASSWORD_LIMIT
    elif unbroken and _LINK.match(value):
        limit = LINK_LIMIT
    elif unbroken:
        limit = TOKEN_LIMIT
    else:
        limit = TEXT_LIMIT
    if len(value) <= limit:
        return value, False
    return value[:limit] + TRIM_MARK, True


def trim_rows(rows: list[dict]) -> tuple[list[dict], list[str]]:
    """(rows with long values cut, the columns where something was cut).
    Applied once to every SQL tool result, so the agent and the client see
    the same values."""
    trimmed: list[str] = []
    out = []
    for row in rows:
        new = {}
        for column, value in row.items():
            new[column], cut = _trim_value(column, value)
            if cut and column not in trimmed:
                trimmed.append(column)
        out.append(new)
    return out, trimmed


# ──────────────────────────────────────────────────────────────────────────────
# Column types
# ──────────────────────────────────────────────────────────────────────────────

def _value_type(value: Any) -> str:
    if isinstance(value, bool):
        return BOOLEAN
    if isinstance(value, (int, float, Decimal)):
        return NUMBER
    if isinstance(value, dt.datetime):
        return DATETIME
    if isinstance(value, dt.date):
        return DATE
    if isinstance(value, (dict, list, tuple)):
        return JSON
    if isinstance(value, str):
        if _ISO_DATE.match(value):
            return DATE
        if _ISO_DATETIME.match(value):
            return DATETIME
        return TEXT
    return OTHER


def _column_type(values: list) -> str:
    types = {_value_type(v) for v in values}
    if not types:
        return TEXT
    if types == {DATE, DATETIME}:
        return DATETIME
    if len(types) == 1:
        return types.pop()
    return TEXT if types <= {TEXT, DATE, DATETIME} else OTHER


def _column_role(name: str, kind: str, values: list) -> str | None:
    if kind == TEXT and values:
        urls = [v for v in values if _URL.match(v.strip())]
        if len(urls) >= URL_SHARE * len(values):
            pictures = [v for v in urls if _IMAGE_EXTENSION.search(v)]
            if _IMAGE_NAME.search(name) or len(pictures) >= URL_SHARE * len(urls):
                return IMAGE
            return URL
    low = name.lower()
    if kind in (NUMBER, TEXT) and (low == "id" or low.endswith("_id") or low.endswith(" id")):
        return ID
    return None


def describe_columns(columns: list[str], rows: list[dict]) -> list[dict]:
    """[{"name", "type", "role"}] for each distinct result column."""
    meta, seen = [], set()
    for name in columns or []:
        if name in seen:
            continue
        seen.add(name)
        values = [row.get(name) for row in rows if row.get(name) is not None]
        kind = _column_type(values)
        meta.append({"name": name, "type": kind, "role": _column_role(name, kind, values)})
    return meta


# ──────────────────────────────────────────────────────────────────────────────
# Views
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class DisplayHint:
    """The agent's request; every part is optional."""
    type: str = AUTO
    x: str = ""
    y: list[str] = field(default_factory=list)
    series: str = ""

    @classmethod
    def parse(cls, display: Any = None, x: Any = None, y: Any = None,
              series: Any = None) -> "DisplayHint":
        kind = str(display or AUTO).strip().lower()
        if isinstance(y, str):
            y = [part for part in re.split(r"[,\s]+", y) if part]
        return cls(type=kind if kind in VIEW_TYPES else AUTO,
                   x=str(x or "").strip(), y=[str(v).strip() for v in y or [] if str(v).strip()],
                   series=str(series or "").strip())


class _Unfit(Exception):
    """This view doesn't fit the result; the message says why."""


class _Result:
    def __init__(self, column_meta: list[dict], rows: list[dict], truncated: bool):
        self.columns = column_meta
        self.rows = rows
        self.truncated = truncated
        self.by_name = {c["name"]: c for c in column_meta}

    def resolve(self, name: str) -> str:
        """The result column the agent meant: exact, case-insensitive, or
        without a table qualifier / quotes."""
        if not name:
            raise _Unfit("no column given")
        if name in self.by_name:
            return name
        bare = name.split(".")[-1].strip('"').strip()
        for candidate in (bare, bare.lower()):
            for col in self.by_name:
                if col == candidate or col.lower() == candidate.lower():
                    return col
        raise _Unfit(f"column '{name}' is not in the result")

    def type(self, name: str) -> str:
        return self.by_name[name]["type"]

    def role(self, name: str) -> str | None:
        return self.by_name[name]["role"]

    def first(self, *, types: tuple = (), exclude: Iterable[str] = ()) -> str | None:
        """The first column of the given types, preferring labels to ids;
        never an image or URL column."""
        skip = set(exclude)
        fits = [c for c in self.columns
                if c["name"] not in skip and c["role"] not in (IMAGE, URL)
                and (not types or c["type"] in types)]
        best = next((c for c in fits if c["role"] != ID), fits[0] if fits else None)
        return best["name"] if best else None

    def measures(self, exclude: Iterable[str] = ()) -> list[str]:
        skip = set(exclude)
        return [c["name"] for c in self.columns
                if c["type"] == NUMBER and c["role"] != ID and c["name"] not in skip]

    def distinct(self, name: str) -> int:
        return len({_key(row.get(name)) for row in self.rows})

    def image(self) -> str | None:
        return next((c["name"] for c in self.columns if c["role"] == IMAGE), None)


def _key(value: Any) -> Any:
    return repr(value) if isinstance(value, (dict, list)) else value


def _table(_: _Result, __: DisplayHint) -> dict:
    return {"type": TABLE}


def _stat(result: _Result, _: DisplayHint) -> dict:
    if len(result.rows) != 1:
        raise _Unfit(f"the result has {len(result.rows)} rows, not one")
    fields = [c["name"] for c in result.columns if c["role"] != IMAGE]
    if not fields or len(fields) > MAX_STAT_FIELDS:
        raise _Unfit(f"a summary shows 1 to {MAX_STAT_FIELDS} values")
    return {"type": STAT, "fields": fields}


def _cards(result: _Result, _: DisplayHint) -> dict:
    image = result.image()
    if image is None:
        raise _Unfit("the result has no image column")
    if not result.rows:
        raise _Unfit("the result is empty")
    title = next((c["name"] for c in result.columns
                  if c["type"] == TEXT and c["role"] is None
                  and any(c["name"].lower() == n or c["name"].lower().endswith("_" + n)
                          for n in _TITLE_NAMES)), None)
    title = title or result.first(types=(TEXT,), exclude=[image])
    fields = [c["name"] for c in result.columns if c["name"] not in (image, title)]
    return {"type": CARDS, "image": image, "title": title, "fields": fields}


def _chart(kind: str):
    def build(result: _Result, hint: DisplayHint) -> dict:
        rows = result.rows
        if not rows:
            raise _Unfit("the result is empty")
        if result.truncated:
            raise _Unfit("the result has more rows than were fetched, so a chart would be "
                         "incomplete; aggregate it in SQL")

        series = result.resolve(hint.series) if hint.series else None
        y = [result.resolve(name) for name in hint.y]
        for name in y:
            if result.type(name) != NUMBER:
                raise _Unfit(f"'{name}' is not numeric")
        if hint.x:
            x = result.resolve(hint.x)
        elif kind == LINE:
            x = (result.first(types=(DATE, DATETIME), exclude=[series or ""])
                 or result.first(types=(TEXT,), exclude=[series or ""])
                 or result.first(types=(NUMBER,), exclude=y + [series or ""]))
        elif kind == SCATTER:
            x = result.first(types=(NUMBER,), exclude=y + [series or ""])
        else:
            x = (result.first(types=(TEXT, DATE, DATETIME, BOOLEAN), exclude=[series or ""])
                 or result.first(exclude=y + [series or ""]))
        if x is None:
            raise _Unfit("no column for the x axis")
        if result.role(x) == IMAGE:
            raise _Unfit(f"'{x}' holds images")
        y = [name for name in y if name != x] or result.measures(exclude=[x, series or ""])
        if not y:
            raise _Unfit("no numeric column to plot")
        y = y[:MAX_MEASURES]

        if series is not None:
            if series in (x, *y):
                raise _Unfit("the series column must differ from x and y")
            if len(y) != 1:
                raise _Unfit("a series chart plots exactly one measure")
            if kind == PIE:
                raise _Unfit("a pie chart has no series")
            limit = MAX_SCATTER_SERIES if kind == SCATTER else MAX_SERIES
            if result.distinct(series) > limit:
                raise _Unfit(f"more than {limit} series")

        points = result.distinct(x)
        if kind == BAR and points > MAX_BAR_CATEGORIES:
            raise _Unfit(f"{points} categories; a bar chart shows at most {MAX_BAR_CATEGORIES}")
        if kind == LINE and points < MIN_LINE_POINTS:
            raise _Unfit("a line chart needs at least two points")
        if kind == PIE:
            if len(y) != 1:
                y = y[:1]
            if not 1 < len(rows) <= MAX_PIE_SLICES or points != len(rows):
                raise _Unfit(f"a pie chart shows 2 to {MAX_PIE_SLICES} distinct slices")
            values = [_number(row.get(y[0])) for row in rows]
            if any(v is not None and v < 0 for v in values) or not sum(v or 0 for v in values):
                raise _Unfit("a pie chart needs positive values")
        if kind == SCATTER:
            if result.type(x) != NUMBER:
                raise _Unfit(f"'{x}' is not numeric")
            y = y[:1]
            if len(rows) < MIN_SCATTER_POINTS:
                raise _Unfit("a scatter plot needs at least three points")
        return {"type": kind, "x": x, "y": y, "series": series}
    return build


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None and not isinstance(value, bool) else None
    except (TypeError, ValueError):
        return None


_BUILDERS = {TABLE: _table, STAT: _stat, CARDS: _cards,
             **{kind: _chart(kind) for kind in CHARTS}}


def _try(kind: str, result: _Result, hint: DisplayHint) -> tuple[dict | None, str]:
    try:
        return _BUILDERS[kind](result, hint), ""
    except _Unfit as exc:
        return None, str(exc)


def _auto(result: _Result) -> dict:
    """The default view without a hint: never a chart (only the agent knows
    the user wants one)."""
    for kind in (CARDS, STAT):
        view, _ = _try(kind, result, DisplayHint())
        if view is not None:
            return view
    return {"type": TABLE}


def _suggested_chart(result: _Result) -> dict | None:
    """A chart offered as an alternative view when the result has the shape
    of one: a single category/time column and numeric measures."""
    if len(result.rows) < 2:
        return None
    dims = [c for c in result.columns
            if c["type"] in (TEXT, DATE, DATETIME) and c["role"] is None]
    if len(dims) != 1 or not result.measures(exclude=[dims[0]["name"]]):
        return None
    kind = LINE if dims[0]["type"] in (DATE, DATETIME) else BAR
    view, _ = _try(kind, result, DisplayHint(type=kind, x=dims[0]["name"]))
    return view


def build_views(column_meta: list[dict], rows: list[dict], *, truncated: bool = False,
                hint: DisplayHint | None = None) -> tuple[list[dict], str]:
    """(views, note): the default view first, then the alternatives. `note`
    says what was shown when the hint asked for something else, or which
    view the hint got; empty without a hint."""
    hint = hint or DisplayHint()
    result = _Result(column_meta, rows, truncated)
    views, note = [], ""
    if hint.type != AUTO:
        view, reason = _try(hint.type, result, hint)
        if view is not None:
            views.append(view)
            note = f"Display: shown as a {_LABELS[hint.type]}."
        else:
            views.append(_auto(result))
            note = (f"Display: a {_LABELS[hint.type]} was not possible ({reason}); "
                    f"shown as a {_LABELS[views[0]['type']]}.")
    else:
        views.append(_auto(result))

    alternatives = [_suggested_chart(result), _try(CARDS, result, hint)[0], {"type": TABLE}]
    types = {v["type"] for v in views}
    for view in alternatives:
        if view is not None and view["type"] not in types:
            views.append(view)
            types.add(view["type"])
    return views, note


def describe_result(columns: list[str], rows: list[dict], *, truncated: bool = False,
                    hint: DisplayHint | None = None) -> dict:
    """{"column_meta", "views", "display_note"} for a result."""
    meta = describe_columns(columns, rows)
    views, note = build_views(meta, rows, truncated=truncated, hint=hint)
    return {"column_meta": meta, "views": views, "display_note": note}


def upgrade_stored(meta: dict) -> dict:
    """Adds column types and views to an answer stored before they existed."""
    rows = meta.get("rows")
    if not isinstance(rows, list) or not rows or meta.get("views"):
        return meta
    columns = meta.get("columns") or list(rows[0].keys())
    # Older answers kept at most 50 rows and didn't record whether more
    # existed: a full 50 may be partial, so no chart is offered for it.
    truncated = meta["truncated"] if "truncated" in meta else len(rows) >= _LEGACY_STORED_ROWS
    described = describe_result(columns, rows, truncated=bool(truncated))
    return {**meta, "column_meta": described["column_meta"], "views": described["views"]}
