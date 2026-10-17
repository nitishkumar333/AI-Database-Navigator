from pathlib import Path

from dotenv import load_dotenv

# Settings reads .env itself, but libraries configured only by environment
# variables (LangSmith tracing) need it in os.environ, before they are used.
load_dotenv(Path(__file__).parent / ".env")

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from app.database import init_db  # noqa: E402
from app.logging_setup import configure_logging  # noqa: E402
from app.observability import configure_tracing, flush as flush_traces  # noqa: E402
from app.services.rate_limiter import RateLimitMiddleware  # noqa: E402
from app.routers import auth, connections, schema, knowledge, query, history, conversations, suggestions  # noqa: E402

app = FastAPI(
    title="SQLNav",
    description="Natural Language → SQL",
    version="1.0.0",
)

# Rate limits. Added before CORS so CORS wraps it: a 429 must still carry the
# CORS headers, or the browser hides it from the frontend as a network error.
app.add_middleware(RateLimitMiddleware)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Retry-After", "X-Rate-Limit"],     # readable by the frontend on a 429
)

# Include routers
app.include_router(auth.router)
app.include_router(connections.router)
app.include_router(schema.router)
app.include_router(knowledge.router)
app.include_router(query.router)
app.include_router(history.router)
app.include_router(conversations.router)
app.include_router(suggestions.router)


@app.on_event("startup")
def on_startup():
    configure_logging()
    configure_tracing()
    init_db()


@app.on_event("shutdown")
def on_shutdown():
    flush_traces()          # send traced runs still queued in the background


@app.get("/")
def root():
    return {"message": "SQLNav Platform API", "docs": "/docs"}


@app.get("/health")
def health():
    return {"status": "healthy"}
