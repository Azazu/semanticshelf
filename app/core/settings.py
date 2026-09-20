"""Application settings, read from the environment (and a `.env` file when present).

No module-level instance: the application factory builds `Settings` when it
runs, so importing the package never requires a database variable and tests
can construct several configurations in one process.
"""

from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ASYNCPG_SCHEME = "postgresql+asyncpg://"

LogLevel = Literal["debug", "info", "warning", "error"]


class Settings(BaseSettings):
    """Everything the service reads from the environment. Documented in docs/reference/settings.md."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = Field(description="SQLAlchemy URL, postgresql+asyncpg:// scheme, required.")
    log_level: LogLevel = "info"
    log_json: bool = True
    readiness_timeout_seconds: float = Field(default=3.0, gt=0)

    @field_validator("database_url")
    @classmethod
    def _require_asyncpg_scheme(cls, value: str) -> str:
        if not value.startswith(ASYNCPG_SCHEME):
            raise ValueError(f"DATABASE_URL must use the {ASYNCPG_SCHEME} scheme")
        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalise_log_level(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value
