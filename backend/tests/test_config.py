"""Settings must survive a real .env file.

This is a regression test for a failure that the rest of the suite could not
see: every other test runs from environment variables, but a deployment reads
`backend/.env`, and pydantic-settings treats a list field there differently.
The result was an import-time crash that only appeared once a .env existed.
"""

from __future__ import annotations

from pathlib import Path

from app.core.config import Settings


def _settings_from(env_file: Path) -> Settings:
    return Settings(_env_file=env_file)  # type: ignore[call-arg]


def test_comma_separated_cors_origins_are_split(tmp_path: Path):
    env = tmp_path / ".env"
    env.write_text(
        "DATABASE_URL=postgresql+asyncpg://u:p@h:5432/db\n"
        "CORS_ORIGINS=http://localhost:5173,https://map.example.la\n",
        encoding="utf-8",
    )
    settings = _settings_from(env)
    assert settings.cors_origins == ["http://localhost:5173", "https://map.example.la"]


def test_a_single_origin_still_becomes_a_list(tmp_path: Path):
    env = tmp_path / ".env"
    env.write_text("CORS_ORIGINS=https://map.example.la\n", encoding="utf-8")
    assert _settings_from(env).cors_origins == ["https://map.example.la"]


def test_blank_origins_yield_an_empty_list(tmp_path: Path):
    env = tmp_path / ".env"
    env.write_text("CORS_ORIGINS=\n", encoding="utf-8")
    assert _settings_from(env).cors_origins == []


def test_admin_endpoints_are_closed_unless_a_token_is_configured(tmp_path: Path):
    env = tmp_path / ".env"
    env.write_text("ENV=prod\n", encoding="utf-8")
    assert _settings_from(env).admin_token == ""


def test_a_password_containing_at_survives_the_url(tmp_path: Path, monkeypatch):
    """The '@' in a password must be percent-encoded, or the driver reads it as
    the start of the host. Documenting the working form here so the shape is not
    rediscovered by debugging a connection failure."""
    # The suite sets DATABASE_URL for the in-memory database, and a real
    # environment variable outranks the .env file.
    monkeypatch.delenv("DATABASE_URL", raising=False)
    env = tmp_path / ".env"
    env.write_text(
        "DATABASE_URL=postgresql+asyncpg://user:pass%40word@db.example.la:5432/aipnicmp\n",
        encoding="utf-8",
    )
    url = _settings_from(env).database_url
    assert url.endswith("@db.example.la:5432/aipnicmp")
    assert "pass%40word" in url
