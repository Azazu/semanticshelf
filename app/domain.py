"""The vocabulary the whole service shares: model keys, value domains, and the
immutable objects repositories hand back.

Nothing here imports the database, HTTP or a model runtime, so every layer may
depend on it and none of it can drag a session into a response. The mapping
`EMBEDDING_MODELS` is the application's authority on which models exist and how
wide their vectors are; the migration that installs the matching database
constraint keeps its own frozen copy, and a unit test holds the two together.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
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
IMPLEMENTED_MODELS: Final[frozenset[str]] = frozenset({CLIP_VIT_L14, DINOV2_LARGE})


@dataclass(frozen=True, slots=True)
class Modality:
    """What a model can be asked for: words, pictures, or both."""

    text: bool
    images: bool

    def __post_init__(self) -> None:
        if not (self.text or self.images):
            raise ValueError("a model that takes neither text nor images embeds nothing")

    @property
    def described(self) -> str:
        """What this model takes, for a refusal a client can act on."""
        if self.text and self.images:
            return "text and pictures"
        return "text" if self.text else "pictures"


#: Which kinds of query each model can answer. One table, because the router
#: refuses an impossible pair before anything is loaded and the service must
#: never have to ask a model what it cannot do — loading a model to find that
#: out is exactly the cost the refusal exists to avoid. Every key of
#: `EMBEDDING_MODELS` appears here, so a model cannot be added without the
#: question being answered; a unit test holds the two tables together.
MODEL_MODALITIES: Final[Mapping[str, Modality]] = {
    CLIP_VIT_L14: Modality(text=True, images=True),  # one joint space
    DINOV2_LARGE: Modality(text=False, images=True),  # no text tower at all
}


class UnknownModelError(LookupError):
    """A model key the application does not declare.

    Raised wherever a key arrives from outside the code — configuration, a
    request, a job row — so every layer reports the same failure for it.
    """


def vector_index_name(model: str) -> str:
    """The name of the vector index serving one model key."""
    return "ix_embeddings_" + model.replace("-", "_")


def dimension_of(model: str) -> int:
    """The declared dimension of a model key, or `KeyError` for an unknown key."""
    return EMBEDDING_MODELS[model]


def modality_of(model: str) -> Modality:
    """What a model key can be asked for.

    Raises `UnknownModelError` rather than `KeyError`, because the key usually
    arrives from a request: every layer reports an unknown model the same way.
    """
    try:
        return MODEL_MODALITIES[model]
    except KeyError as exc:
        raise UnknownModelError(f"unknown embedding model: {model!r}") from exc


# --- immutable objects -------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Narrowing:
    """Which assets a search or a listing is willing to consider.

    Three conditions, all optional and all combinable: every one of `tags_all`
    present, at least one of `tags_any` present, and each entry of `meta` equal
    at the top level of the asset's metadata. What may be in them — how a tag is
    normalised, how a metadata key is shaped, how many conditions are allowed —
    is the parser's business (`app/services/tagging.py`); what this carries is
    the answer, already checked.

    An empty narrowing is falsy, and a falsy narrowing is never applied: it must
    cost nothing, because most searches carry one.
    """

    tags_all: tuple[str, ...] = ()
    tags_any: tuple[str, ...] = ()
    meta: Mapping[str, str] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.tags_all or self.tags_any or self.meta)


#: The narrowing that narrows nothing: the default of every search and listing,
#: and a value rather than a new object each time, because it is immutable and
#: most requests carry it.
NO_NARROWING: Final[Narrowing] = Narrowing()


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
