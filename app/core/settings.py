"""Application settings, read from the environment (and a `.env` file when present).

No module-level instance: the application factory builds `Settings` when it
runs, so importing the package never requires a database variable and tests
can construct several configurations in one process.
"""

from pathlib import Path
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.domain import CLIP_VIT_L14, IMPLEMENTED_MODELS

ASYNCPG_SCHEME = "postgresql+asyncpg://"

LogLevel = Literal["debug", "info", "warning", "error"]

DEFAULT_MODEL_CACHE = Path(".data/models")
DEFAULT_CLIP_CHECKPOINT = "openai/clip-vit-large-patch14"


class Settings(BaseSettings):
    """Everything the service reads from the environment. Documented in docs/reference/settings.md."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = Field(description="SQLAlchemy URL, postgresql+asyncpg:// scheme, required.")
    log_level: LogLevel = "info"
    log_json: bool = True
    readiness_timeout_seconds: float = Field(default=3.0, gt=0)

    # --- embedding models ---------------------------------------------------
    # The default is what this build implements, not every key the schema
    # knows: a default configuration must be able to start.
    enabled_models: tuple[str, ...] = tuple(sorted(IMPLEMENTED_MODELS))
    #: Loaded by the lifespan at start; empty means nothing loads until asked.
    model_warmup: tuple[str, ...] = ()
    #: Where model weights are cached. Gitignored, and never inside the package.
    model_cache: Path = DEFAULT_MODEL_CACHE
    #: The checkpoint behind the `clip-vit-l14` key. A compatible fine-tune or
    #: mirror may be substituted; one of a different width is refused at load.
    clip_model_name: str = DEFAULT_CLIP_CHECKPOINT
    #: 0 leaves torch its own default of one thread per physical core.
    torch_num_threads: int = Field(default=0, ge=0)
    embed_batch_size: int = Field(default=8, gt=0)
    #: Threads that load models and run inference, away from the event loop.
    inference_workers: int = Field(default=2, gt=0)

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

    @field_validator("enabled_models", "model_warmup", mode="before")
    @classmethod
    def _split_comma_separated(cls, value: object) -> object:
        """`ENABLED_MODELS=clip-vit-l14,dinov2-large` rather than JSON."""
        if isinstance(value, str):
            return tuple(item.strip() for item in value.split(",") if item.strip())
        return value

    @model_validator(mode="after")
    def _only_models_this_build_implements(self) -> Self:
        """Refuse to start on a configuration the code cannot honour.

        An enabled key without an adapter would fail at the first request
        instead of at start, and a warm-up key that is not enabled would load
        weights nothing can use.
        """
        unknown = [key for key in self.enabled_models if key not in IMPLEMENTED_MODELS]
        if unknown:
            raise ValueError(
                f"ENABLED_MODELS names models this build does not implement: {', '.join(unknown)}; "
                f"implemented: {', '.join(sorted(IMPLEMENTED_MODELS))}"
            )
        not_enabled = [key for key in self.model_warmup if key not in self.enabled_models]
        if not_enabled:
            raise ValueError(
                f"MODEL_WARMUP names models that are not enabled: {', '.join(not_enabled)}"
            )
        return self


__all__ = ["CLIP_VIT_L14", "DEFAULT_CLIP_CHECKPOINT", "DEFAULT_MODEL_CACHE", "LogLevel", "Settings"]
