"""Application settings, read from the environment (and a `.env` file when present).

No module-level instance: the application factory builds `Settings` when it
runs, so importing the package never requires a database variable and tests
can construct several configurations in one process.
"""

from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.domain import CLIP_VIT_L14, IMPLEMENTED_MODELS

ASYNCPG_SCHEME = "postgresql+asyncpg://"

LogLevel = Literal["debug", "info", "warning", "error"]

DEFAULT_MODEL_CACHE = Path(".data/models")
DEFAULT_CLIP_CHECKPOINT = "openai/clip-vit-large-patch14"
DEFAULT_MEDIA_ROOT = Path(".data/media")
MIB = 1024 * 1024


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
    #: `NoDecode` because a tuple is a complex type: without it the environment
    #: source tries to read the value as JSON before any validator runs, and
    #: `ENABLED_MODELS=clip-vit-l14` fails to parse instead of being split below.
    enabled_models: Annotated[tuple[str, ...], NoDecode] = tuple(sorted(IMPLEMENTED_MODELS))
    #: Loaded by the lifespan at start; empty means nothing loads until asked.
    model_warmup: Annotated[tuple[str, ...], NoDecode] = ()
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

    # --- media ---------------------------------------------------------------
    #: Where an asset's bytes live. Outside any directory served by path, and
    #: never created by the service: a mistyped root is reported by readiness
    #: rather than silently created beside the real one.
    media_root: Path = DEFAULT_MEDIA_ROOT
    #: The bound on a whole request body, enforced while it is read.
    max_upload_bytes: int = Field(default=20 * MIB, gt=0)
    #: Refused before any pixel is allocated, at exactly this number.
    max_image_pixels: int = Field(default=40_000_000, gt=0)
    min_image_side: int = Field(default=32, gt=0)
    #: A margin for `storage prune` run against a store this service does not
    #: write; the guarantee against deleting a live upload is the advisory lock.
    prune_min_age_seconds: int = Field(default=3600, gt=0)

    # --- indexing ------------------------------------------------------------
    #: How long a claim on a job is good for. Nothing refreshes it: a runner
    #: that dies releases its work when this expires, and the claim's own
    #: expiry value is the token that keeps a late finish from landing.
    job_lease_seconds: int = Field(default=600, gt=0)
    #: How many times a job may be attempted before it is failed for good.
    job_max_attempts: int = Field(default=3, gt=0)
    #: How many jobs a single run of a runner takes. A runner that drained
    #: while work remained would never end.
    worker_batch_size: int = Field(default=4, gt=0)

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
        """`ENABLED_MODELS=clip-vit-l14,dinov2-large` rather than JSON.

        Reached only because the fields are marked `NoDecode`; an empty
        variable means an empty tuple, not a one-element tuple of nothing.
        """
        if isinstance(value, str):
            value = tuple(item.strip() for item in value.split(",") if item.strip())
        if isinstance(value, tuple | list):
            # A key named twice is one enabled model, not two: duplicates would
            # become duplicate indexing jobs per asset.
            return tuple(dict.fromkeys(value))
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
