"""
One logging setup for the backend's own terminal output.

All lines share one handler and one format, `HH:MM:SS LEVEL [area] message`:

- `agent` (services/agent/trace_log.py): every LLM and tool call of a chat
  turn. Level AGENT_LOG_LEVEL (default INFO).
- `jobs` (services/schema_index/job_log.py): profile, index and describe
  steps of the schema background jobs. Level JOB_LOG_LEVEL (default INFO).
- every other `app.*` module: warnings and errors only, so their INFO and
  DEBUG lines never clutter the terminal.

The areas are child loggers of "sqlnav" with propagate off, so they print once
even when something else configures the root logger (evaluation runs call
logging.basicConfig). The `app.*` handler is added only when nobody else has
configured the root logger; otherwise their records go wherever it sends them.
"""
from __future__ import annotations

import logging
import sys
import threading

from app.config import get_settings

ROOT = "sqlnav"
_lock = threading.Lock()
_configured = False


class _Formatter(logging.Formatter):
    """Shows `[agent]` for "sqlnav.agent" and `[services.x.y]` for "app.services.x.y"."""

    def format(self, record: logging.LogRecord) -> str:
        record.area = record.name.split(".", 1)[1] if record.name.startswith(("sqlnav.", "app.")) \
            else record.name
        return super().format(record)


def _level(name: str, default: int) -> int:
    return getattr(logging, (name or "").upper(), default)


def configure_logging() -> None:
    """Idempotent; called at startup and by get_logger()."""
    global _configured
    if _configured:
        return
    with _lock:
        if _configured:
            return
        settings = get_settings()
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(_Formatter("%(asctime)s %(levelname)s [%(area)s] %(message)s", "%H:%M:%S"))

        root = logging.getLogger(ROOT)
        root.addHandler(handler)
        root.propagate = False
        logging.getLogger(f"{ROOT}.agent").setLevel(_level(settings.AGENT_LOG_LEVEL, logging.INFO))
        logging.getLogger(f"{ROOT}.jobs").setLevel(_level(settings.JOB_LOG_LEVEL, logging.INFO))

        if not logging.getLogger().handlers:       # nobody configured logging (uvicorn)
            app = logging.getLogger("app")
            app.setLevel(logging.WARNING)
            app.addHandler(handler)
            app.propagate = False
        _configured = True


def get_logger(area: str) -> logging.Logger:
    """The logger of one output area ("agent", "jobs")."""
    configure_logging()
    return logging.getLogger(f"{ROOT}.{area}")
