"""The vocabulary the whole service shares: model keys, value domains, and the
immutable objects repositories hand back.

Nothing here imports the database, HTTP or a model runtime, so every layer may
depend on it and none of it can drag a session into a response. The mapping
`EMBEDDING_MODELS` is the application's authority on which models exist and how
wide their vectors are; the migration that installs the matching database
constraint keeps its own frozen copy, and a unit test holds the two together.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Literal, get_args
from uuid import UUID

# --- value domains -----------------------------------------------------------

ContentType = Literal["image/jpeg", "image/png", "image/webp"]
FileExtension = Literal["jpg", "png", "webp"]
AssetSource = Literal["upload", "folder"]
JobStatus = Literal["pending", "running", "done", "failed"]

CONTENT_TYPES: Final[tuple[ContentType, ...]] = get_args(ContentType)
FILE_EXTENSIONS: Final[tuple[FileExtension, ...]] = get_args(FileExtension)
ASSET_SOURCES: Final[tuple[AssetSource, ...]] = get_args(AssetSource)
JOB_STATUSES: Final[tuple[JobStatus, ...]] = get_args(JobStatus)

# The file extension each accepted content type is stored under.
EXTENSION_BY_CONTENT_TYPE: Final[Mapping[ContentType, FileExtension]] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}

# --- embedding models --------------------------------------------------------

CLIP_VIT_L14: Final = "clip-vit-l14"
DINOV2_LARGE: Final = "dinov2-large"

#: Model key -> vector dimension. A key is the identity of an embedding together
#: with its asset, so it is stable forever: a model whose output space changes
#: gets a new key, a migration and a re-index, never a redefinition of this one.
EMBEDDING_MODELS: Final[Mapping[str, int]] = {
    CLIP_VIT_L14: 768,  # openai/clip-vit-large-patch14, joint text-image space
    DINOV2_LARGE: 1024,  # facebook/dinov2-large, CLS token
}


#: The subset of `EMBEDDING_MODELS` this build has an adapter for. The schema
#: knows every key the project will ever store, because a migration is written
#: once; the code catches up one change at a time, and configuration may only
#: enable what the code can actually run. `app/ml/registry.py` declares the same
#: set as a table of factories, and a unit test holds the two together.
IMPLEMENTED_MODELS: Final[frozenset[str]] = frozenset({CLIP_VIT_L14})


def vector_index_name(model: str) -> str:
    """The name of the vector index serving one model key."""
    return "ix_embeddings_" + model.replace("-", "_")


def dimension_of(model: str) -> int:
    """The declared dimension of a model key, or `KeyError` for an unknown key."""
    return EMBEDDING_MODELS[model]


# --- immutable objects -------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Asset:
    """An indexed image as the store keeps it. The file path is derived from the
    id and the extension, never stored."""

    id: UUID
    created_at: datetime
    sha256: str
    content_type: str
    file_ext: str
    width: int
    height: int
    size_bytes: int
    original_filename: str | None
    source: str
    tags: tuple[str, ...]
    meta: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class Embedding:
    """One model's vector for one asset."""

    id: UUID
    asset_id: UUID
    model: str
    vector: tuple[float, ...]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class IndexingJob:
    """One unit of extraction work. The claim protocol arrives with the worker."""

    id: UUID
    asset_id: UUID
    model: str
    status: str
    attempts: int
    available_at: datetime
    lease_expires_at: datetime | None
    last_error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


@dataclass(frozen=True, slots=True)
class NeighbourHit:
    """One result of a nearest-neighbour lookup: which asset, and how far.

    `distance` is the cosine distance in [0, 2]; the search layer turns it into
    the score the API exposes.
    """

    asset_id: UUID
    distance: float
