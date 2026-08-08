"""Application settings, loaded from environment or backend/.env."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql+asyncpg://aipnicmp:aipnicmp@127.0.0.1:5432/aipnicmp"
    database_url_sync: str = "postgresql+psycopg://aipnicmp:aipnicmp@127.0.0.1:5432/aipnicmp"

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"

    # App
    env: str = "dev"
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"
    # NoDecode stops pydantic-settings trying to JSON-parse this before the
    # validator below runs — without it, a plain comma-separated CORS_ORIGINS in
    # .env raises at import time instead of being split.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )

    # Ingestion limits
    max_batch_records: int = 1000
    max_plausible_speed_mps: float = 90.0
    max_gps_accuracy_m: float = 100.0
    max_record_age_days: int = 30

    # Security
    require_record_signature: bool = True
    jwt_secret: str = "dev-only-secret"
    jwt_expire_minutes: int = 720
    # Empty means the admin endpoints stay closed. Never default this to a value.
    admin_token: str = ""

    # Aggregation
    h3_resolution: int = 8
    tile_min_devices: int = 2

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        """Accept a comma-separated string from the environment."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @property
    def is_dev(self) -> bool:
        return self.env.lower() in {"dev", "development", "local"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
