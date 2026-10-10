"""
Must be imported before anything from the backend `app` package.

- Loads env vars from evaluation/.env, then backend/.env as a fallback
  (existing variables are never overridden, so shell exports win).
- Forces AGENT_MODE=evaluation so the agent stops right after the SQL tool
  succeeds and never spends tokens on the final natural-language answer.
- Puts backend/ on sys.path so `import app...` resolves to the real agent code.
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

EVAL_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVAL_DIR.parent
BACKEND_DIR = REPO_ROOT / "backend"

load_dotenv(EVAL_DIR / ".env")
load_dotenv(BACKEND_DIR / ".env")
os.environ["AGENT_MODE"] = "evaluation"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
