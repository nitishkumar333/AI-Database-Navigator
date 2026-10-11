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
    # "evaluation": stop as soon as the SQL tool succeeds, skipping the
    #               final answer-generation LLM call (saves tokens in evals).
    AGENT_MODE: str = "production"
    ENCRYPTION_KEY: str = ""  # Fernet key, auto-generated if empty

    # Schema profiling (services/schema_index). Profiling reads catalogs and
    # planner statistics only; describing spends one LLM call per table.
    SCHEMA_PROFILING_ENABLED: bool = True
    SCHEMA_DESCRIBE_ENABLED: bool = True
    SCHEMA_CHECK_INTERVAL_S: int = 300        # how often to look for schema changes
    SCHEMA_DESCRIBE_MAX_TABLES: int = 50      # per refresh; the rest follow on later refreshes
    
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
