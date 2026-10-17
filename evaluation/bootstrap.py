"""
Must be imported before anything from the backend `app` package.

- Loads env vars from evaluation/.env, then backend/.env as a fallback
  (existing variables are never overridden, so shell exports win).
- Forces AGENT_MODE=evaluation so the agent stops right after it submits its
  answer (submit_answer) and never spends tokens on the final natural-language
  answer.
- Turns LangSmith tracing off: backend/.env may switch it on for the app.
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
# langsmith reads LANGSMITH_* before LANGCHAIN_*, so these win over either.
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGSMITH_TRACING_V2"] = "false"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
