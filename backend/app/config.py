from pydantic_settings import BaseSettings
from functools import lru_cache
import os


class Settings(BaseSettings):
    APP_NAME: str = "SQLNav"
    SECRET_KEY: str = "change-this-to-a-secure-random-key-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    DATABASE_URL: str = ""
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_MODEL: str = "deepseek-flash"  # or "deepseek-v4-pro"
    DEEPSEEK_THINKING: bool = False  # thinking mode: slower, ignores temperature
    LLM_PROVIDER: str = "gemini"  # "gemini" | "groq" | "deepseek"
    # "production": full agent loop (SQL tool -> natural-language answer).
    # "evaluation": stop as soon as an answer is submitted (submit_answer),
    #               skipping the final answer-writing LLM call (saves tokens in evals).
    AGENT_MODE: str = "production"
    # Terminal log of every agent LLM call and tool call (services/agent/trace_log.py):
    # INFO = calls with parameters and results, DEBUG = also full tool output, WARNING = off.
    AGENT_LOG_LEVEL: str = "INFO"
    JOB_LOG_LEVEL: str = "INFO"          # schema background jobs: INFO, WARNING (problems only), ERROR (off)
    # The agent's system prompt holds the full schema (every column of every
    # allowed table) when it fits this size; above it, only the table list
    # (names, row counts, descriptions) and the agent reads columns with its
    # describe_tables tool.
    AGENT_FULL_SCHEMA_MAX_CHARS: int = 32_000   # ~8k tokens
    # Earlier turns of a conversation the agent sees (services/agent/history.py):
    # the most recent AGENT_HISTORY_FULL_TURNS may be sent in full, older ones in
    # short form (question, final SQL, first result rows, reply), all within
    # AGENT_HISTORY_MAX_CHARS. The current turn is always sent in full.
    AGENT_HISTORY_FULL_TURNS: int = 2
    AGENT_HISTORY_MAX_CHARS: int = 24_000       # ~6k tokens
    ENCRYPTION_KEY: str = ""  # Fernet key, auto-generated if empty

    # Schema profiling (services/schema_index). Profiling reads catalogs and
    # planner statistics only; describing spends one LLM call per table.
    SCHEMA_PROFILING_ENABLED: bool = True
    SCHEMA_DESCRIBE_ENABLED: bool = True
    SCHEMA_CHECK_INTERVAL_S: int = 300        # how often to look for schema changes
    SCHEMA_DESCRIBE_MAX_TABLES: int = 50      # re-index after this many new descriptions (and when KB tables are done)

    # Schema retrieval (services/schema_index: index_store, hybrid). Table and
    # column documents plus low-cardinality text values are indexed in the app
    # database (pgvector + pg_trgm) and ranked with reciprocal rank fusion.
    # Without pgvector the agent falls back to in-memory keyword search; without
    # a Jina key the index uses trigram and value matching only.
    SCHEMA_RETRIEVAL_ENABLED: bool = True
    JINA_API_KEY: str = ""
    JINA_EMBEDDING_MODEL: str = "jina-embeddings-v5-text-small"
    EMBEDDING_DIM: int = 1024
    # Text columns with at most this many distinct values have every value indexed.
    SCHEMA_VALUE_INDEX_MAX_DISTINCT: int = 1000
    # When the prompt holds only the table list (schema over AGENT_FULL_SCHEMA_MAX_CHARS),
    # the tables retrieved for the question are added in full, up to:
    SCHEMA_LINK_MAX_TABLES: int = 8
    SCHEMA_LINK_MAX_CHARS: int = 24_000   # ~6k tokens

    # API rate limits (services/rate_limiter.py): "count/seconds", comma-separated
    # for several windows; an empty value turns that limit off.
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_API_IP: str = "10/60"                # every /api request, per IP
    RATE_LIMIT_AUTH_IP: str = "10/60,50/3600"        # login, register, per IP
    RATE_LIMIT_GUEST_IP: str = "5/600,20/86400"      # guest logins (new user each), per IP
    RATE_LIMIT_CHAT_USER: str = "5/60,60/3600"       # chat questions, per user
    RATE_LIMIT_CHAT_IP: str = "10/60,150/3600"       # chat questions, per IP
    RATE_LIMIT_SUGGESTIONS_USER: str = "10/60,120/3600"  # question suggestions, per user
    RATE_LIMIT_HEAVY_USER: str = "10/600"            # add/test connection, re-profile, per user

    # Guest user preloaded DB connection config
    GUEST_DB_HOST: str = "localhost"
    GUEST_DB_PORT: int = 5432
    GUEST_DB_NAME: str = "shop"
    GUEST_DB_USER: str = "postgres"
    GUEST_DB_PASSWORD: str = "password"
    CHECKPOINT_DB_PATH: str = "checkpoints.sqlite"

    class Config:
        env_file = ".env"
        extra = "allow"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
