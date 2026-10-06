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
    GEMINI_MODEL: str = "gemini-2.5-flash"
    ENCRYPTION_KEY: str = ""  # Fernet key, auto-generated if empty
    
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
