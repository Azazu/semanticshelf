"""Application settings, read from the environment (and a `.env` file when present).

No module-level instance: the application factory builds `Settings` when it
runs, so importing the package never requires a database variable and tests
can construct several configurations in one process.
"""

import re
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.domain import (
    CLIP_VIT_L14,
    IMPLEMENTED_MODELS,
    IMPLEMENTED_QUERY_ENCODERS,
    INLINE_RUNNER,
    QUERY_ENCODERS,
    IndexingRunner,
)

ASYNCPG_SCHEME = "postgresql+asyncpg://"

LogLevel = Literal["debug", "info", "warning", "error"]

DEFAULT_MODEL_CACHE = Path(".data/models")
DEFAULT_CLIP_CHECKPOINT = "openai/clip-vit-large-patch14"
DEFAULT_DINOV2_CHECKPOINT = "facebook/dinov2-large"
#: The commits those two names resolved to when this repository verified them.
#: A checkpoint name points at whatever a repository holds today; a commit is
#: the same weights a year from now, which is what a model key has to mean
#: (ADR-007).
DEFAULT_CLIP_REVISION = "32bd64288804d66eefd0ccbe215aa642df71cc41"
DEFAULT_DINOV2_REVISION = "47b73eefe95e8d44ec3623f8890bd894b6ea2d6c"
#: What a revision may be. A branch or a tag is accepted by the model hub and
#: resolves at load time, which is the defect this pin exists to remove, so only
#: a full commit will do — an abbreviated one is refused as well, because it is
#: a prefix and a repository may grow a second object that shares it.
#:
#: No anchors, and matched with `fullmatch`: `$` also matches immediately before
#: a final newline, so `^[0-9a-f]{40}$` accepts a 41-character value ending in
#: one. A variable read from a file or pasted with its line ending would then
#: pass configuration and reach the hub as `%0A` in a URL — refused there, at
#: the first load, instead of here at startup.
COMMIT = re.compile(r"[0-9a-f]{40}")
DEFAULT_MEDIA_ROOT = Path(".data/media")
MIB = 1024 * 1024

#: Where the migration scripts are, computed from this file's own place: from
#: `app/core/` two levels up is the repository root, and the migrations sit
#: beside `app/` there. That is right for a checkout and wrong for an installed
#: package — in an image the package lives inside the virtual environment, where
#: one level up is `site-packages` and `alembic` there is the *library*, which
#: has no revisions in it. So it is a default rather than a fact, and a
#: deployment that puts the migrations elsewhere says where (change 15).
DEFAULT_ALEMBIC_DIR = Path(__file__).resolve().parent.parent.parent / "alembic"


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
    #: The commit of that checkpoint to read. Configuration rather than a
    #: constant, because the name above is configuration: a substituted
    #: checkpoint needs a commit of its own, which only its operator knows.
    clip_revision: str = DEFAULT_CLIP_REVISION
    #: The checkpoint behind the `dinov2-large` key, under the same rule: a
    #: mirror or compatible fine-tune is fine, a different width is refused at
    #: load rather than stored.
    dinov2_model_name: str = DEFAULT_DINOV2_CHECKPOINT
    #: The commit of that checkpoint to read, under the same rule as CLIP's.
    dinov2_revision: str = DEFAULT_DINOV2_REVISION
    #: Which query encoders this build runs. Empty by default: an encoder is
    #: gigabytes of weights for a question most deployments do not ask, and
    #: enabling one must be a decision rather than an inheritance.
    enabled_query_encoders: Annotated[tuple[str, ...], NoDecode] = ()
    #: 0 leaves torch its own default of one thread per physical core.
    torch_num_threads: int = Field(default=0, ge=0)
    embed_batch_size: int = Field(default=8, gt=0)
    #: Threads that load models and run inference, away from the event loop.
    inference_workers: int = Field(default=2, gt=0)

    #: Where the migration scripts are. Only the readiness probe reads it: it
    #: compares the database's revision with the head of these scripts, and a
    #: probe that cannot find them reports "code head none" rather than ready.
    alembic_dir: Path = DEFAULT_ALEMBIC_DIR

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
    #: while work remained would never end — and the bound is also what lets
    #: several runners share a queue and what keeps a stop from waiting for an
    #: unbounded amount of work.
    worker_batch_size: int = Field(default=4, gt=0)
    #: Which runner carries out queued work. `inline` (the default) is the
    #: runner inside whatever process created it — the API after a response, a
    #: command after its import — so a deployment nobody configured still
    #: indexes what it accepts. `worker` leaves all of it to
    #: `semanticshelf worker`, and nothing else executes anything.
    indexing_runner: IndexingRunner = INLINE_RUNNER
    #: How long a runner of its own waits before looking again when the queue
    #: held nothing for it. It is a floor on how late a vector can be, and the
    #: cost of not having it is a claim query in a loop; two seconds is the
    #: trade this service makes (change 13, design decision 7).
    worker_poll_seconds: float = Field(default=2.0, gt=0)

    # --- search --------------------------------------------------------------
    #: How hard the vector index looks for each search. Raised per query to at
    #: least the depth the page asks for and the row beyond it that answers
    #: `has_more` (`limit + offset + 1`), so a deep page does not quietly get a
    #: worse ranking than a shallow one; 1000 is pgvector's own maximum for
    #: `hnsw.ef_search` and the most candidates one scan yields, which is why
    #: the deepest page ends at `limit + offset` = 999.
    hnsw_ef_search: int = Field(default=40, gt=0, le=1000)

    @field_validator("database_url")
    @classmethod
    def _require_asyncpg_scheme(cls, value: str) -> str:
        if not value.startswith(ASYNCPG_SCHEME):
            raise ValueError(f"DATABASE_URL must use the {ASYNCPG_SCHEME} scheme")
        return value

    def _revision_in_effect(
        self, name_field: str, revision_field: str, default_name: str
    ) -> str | None:
        """The commit to read a checkpoint at, or `None` when it must not be pinned.

        A revision belongs to the repository it is a commit of. An operator who
        configured one meant it, whatever the name says. One left at its default
        belongs to the default checkpoint, so it is applied only while that is
        the checkpoint being read — a substituted name inherits nothing and
        loads exactly as it did before this rule existed.
        """
        if revision_field in self.model_fields_set:
            return str(getattr(self, revision_field))
        substituted = getattr(self, name_field) != default_name
        return None if substituted else str(getattr(self, revision_field))

    @property
    def clip_revision_in_effect(self) -> str | None:
        """The commit `clip-vit-l14` is read at, or `None` when it is unpinned."""
        return self._revision_in_effect("clip_model_name", "clip_revision", DEFAULT_CLIP_CHECKPOINT)

    @property
    def dinov2_revision_in_effect(self) -> str | None:
        """The commit `dinov2-large` is read at, or `None` when it is unpinned."""
        return self._revision_in_effect(
            "dinov2_model_name", "dinov2_revision", DEFAULT_DINOV2_CHECKPOINT
        )

    @field_validator("clip_revision", "dinov2_revision")
    @classmethod
    def _require_a_commit(cls, value: str, info: ValidationInfo) -> str:
        """A revision names one immutable object or it names nothing useful.

        `main` is a valid revision to the model hub and a moving target to
        everyone else: it would read as pinned and pin nothing, which is worse
        than the unpinned load it replaced.
        """
        if not COMMIT.fullmatch(value):
            raise ValueError(
                f"{(info.field_name or '').upper()} must be a full 40-character commit "
                "(lowercase hexadecimal); a branch, a tag or an abbreviated hash resolves "
                "at load time, which is what pinning exists to prevent"
            )
        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalise_log_level(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("enabled_models", "model_warmup", "enabled_query_encoders", mode="before")
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
        runnable = (*self.enabled_models, *self.enabled_query_encoders)
        not_enabled = [key for key in self.model_warmup if key not in runnable]
        if not_enabled:
            raise ValueError(
                f"MODEL_WARMUP names models that are not enabled: {', '.join(not_enabled)}"
            )
        unknown_encoders = [
            key for key in self.enabled_query_encoders if key not in IMPLEMENTED_QUERY_ENCODERS
        ]
        if unknown_encoders:
            raise ValueError(
                "ENABLED_QUERY_ENCODERS names encoders this build does not implement: "
                f"{', '.join(unknown_encoders)}; "
                f"implemented: {', '.join(sorted(IMPLEMENTED_QUERY_ENCODERS)) or 'none'}"
            )
        # An encoder answers in another model's space, so without that model
        # there is nothing for its vectors to be compared with: a search would
        # return an empty page and look like a corpus problem.
        spaceless = [
            f"{key} (needs {QUERY_ENCODERS[key]})"
            for key in self.enabled_query_encoders
            if QUERY_ENCODERS[key] not in self.enabled_models
        ]
        if spaceless:
            raise ValueError(
                "ENABLED_QUERY_ENCODERS names encoders whose model is not enabled: "
                f"{', '.join(spaceless)}"
            )
        return self


__all__ = [
    "CLIP_VIT_L14",
    "DEFAULT_CLIP_CHECKPOINT",
    "DEFAULT_DINOV2_CHECKPOINT",
    "DEFAULT_MODEL_CACHE",
    "LogLevel",
    "Settings",
]
