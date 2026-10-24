"""Runtime configuration, read from environment variables and an optional .env file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "db" / "migrations"


class Settings(BaseSettings):
    """Settings for the pipeline. Nothing here is a secret by default."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str | None = Field(
        default=None, description="PostgreSQL URL; SQLite is used if unset"
    )
    voltia_local_db: Path = Field(default=REPO_ROOT / "pipeline" / "data" / "voltia.sqlite")
    google_generative_ai_api_key: str | None = None

    xm_base_url: str = "https://servapibi.xm.com.co"
    http_timeout_s: float = 120.0
    history_start: str = "2018-01-01"
    hourly_retention_days: int = 90
    revision_window_days: int = 7

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            url = self.database_url
            if url.startswith("postgres://"):
                url = "postgresql://" + url.removeprefix("postgres://")
            if url.startswith("postgresql://"):
                url = "postgresql+psycopg://" + url.removeprefix("postgresql://")
            return url
        self.voltia_local_db.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{self.voltia_local_db.as_posix()}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
