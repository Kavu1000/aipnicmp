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

    # Sign-in with Google.
    #
    # The OAuth client id, which is public by design — it identifies this
    # application to Google and appears in the page. There is no client secret
    # here because the browser performs the sign-in and the server only
    # verifies the resulting token's signature; a secret would add a thing to
    # leak without adding a check.
    google_client_id: str = ""

    # Sign-in through Firebase Authentication, as an alternative to the Google
    # button above.
    #
    # Both end in the same place — a signed token this server verifies and an
    # address it trusts — and both are accepted at once, because they differ
    # only in who keeps the list of sites allowed to sign people in. With the
    # Google button that list lives in the Cloud Console project that owns the
    # client id; with Firebase it is the Authorized domains list in the
    # Firebase console. A deployment that cannot reach the first can own the
    # second, which is the whole reason this exists.
    #
    # Empty means Firebase tokens are refused outright — a server that was
    # never told which Firebase project it belongs to has no audience to check
    # against, and an unchecked audience would accept a token minted by any
    # Firebase project on earth.
    firebase_project_id: str = ""

    # Whether the map and dashboard require an approved account.
    #
    # On by default: a deployment that forgets to configure this should be
    # closed, not open. Set AUTH_ENABLED=false only for local development.
    auth_enabled: bool = True

    # Whether a stranger with no account may see the public preview — the
    # combined-network map and headline numbers only, at /api/v1/public/*.
    #
    # On by default, because letting an anonymous visitor in is the entire
    # purpose of that router. Set PUBLIC_PREVIEW_ENABLED=false if a data
    # owner ever asks for it to come down; every route under /public then
    # answers 404, not 403 — 403 would confirm the router still exists.
    public_preview_enabled: bool = True

    # The accounts that may approve others, as a comma-separated list of email
    # addresses. Without at least one, nobody can ever be approved — the first
    # super admin cannot approve themselves into existence.
    #
    # These addresses are approved automatically on first sign-in. Everyone
    # else waits. Deliberately config rather than a database seed, so that
    # losing access to every super admin account is recoverable.
    super_admin_emails: Annotated[list[str], NoDecode] = Field(default_factory=list)

    # Cookies are marked Secure unless this is a development environment. The
    # session cookie carries the whole session, and HTTPS is what stops it
    # being read off the wire.
    session_cookie_name: str = "aipnicmp_session"

    # Aggregation
    h3_resolution: int = 8
    tile_min_devices: int = 2

    # How long an exact GPS fix is kept before it is replaced by the centre of
    # the hexagon it already belongs to.
    #
    # A collector's readings are a fix every ten seconds while they moved, which
    # together is a record of a person's movements. The map has never shown it —
    # it publishes hexagons — but holding it forever is a different promise from
    # the one the platform makes to the people carrying the phones.
    #
    # Ninety days leaves room to investigate a suspect device or re-derive cell
    # positions from fresh data before the precision goes. Set to 0 to keep
    # exact fixes indefinitely, which is a decision worth making deliberately.
    retention_precise_days: int = 90

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        """Accept a comma-separated string from the environment."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @field_validator("super_admin_emails", mode="before")
    @classmethod
    def _split_super_admins(cls, v: object) -> object:
        """Comma-separated, and lowercased — addresses are compared, and case
        is not part of an address anyone means to type."""
        if isinstance(v, str):
            return [email.strip().lower() for email in v.split(",") if email.strip()]
        if isinstance(v, list):
            return [str(email).strip().lower() for email in v]
        return v

    @property
    def is_dev(self) -> bool:
        return self.env.lower() in {"dev", "development", "local"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
