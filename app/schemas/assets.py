"""What an asset looks like on the wire.

Separate from the ORM row on purpose: the representation is a contract with
clients and changes only additively, while the table is free to change with the
schema. Nothing here reaches into a session.
"""

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Self
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.errors import ProblemDetails
from app.domain import Asset

DUPLICATE_TYPE = "/errors/duplicate-asset"


class AssetLinks(BaseModel):
    """Where the bytes are. The paths are the API's, never the filesystem's."""

    file: str
    thumbnail: str


class AssetRead(BaseModel):
    """One asset, as every endpoint returns it."""

    id: UUID
    created_at: datetime
    content_type: str
    width: int
    height: int
    size_bytes: int
    sha256: str
    original_filename: str | None
    source: str
    tags: list[str]
    meta: dict[str, Any]
    index_status: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Model key to the state of that model's newest indexing job: pending, running, "
            "done or failed. Derived from the queue, never stored; empty while an asset has "
            "no work at all."
        ),
    )
    links: AssetLinks

    @classmethod
    def of(
        cls, asset: Asset, *, prefix: str, index_status: Mapping[str, str] | None = None
    ) -> Self:
        return cls(
            id=asset.id,
            created_at=asset.created_at,
            content_type=asset.content_type,
            width=asset.width,
            height=asset.height,
            size_bytes=asset.size_bytes,
            sha256=asset.sha256,
            original_filename=asset.original_filename,
            source=asset.source,
            tags=list(asset.tags),
            meta=dict(asset.meta),
            index_status=dict(index_status or {}),
            links=AssetLinks(
                file=f"{prefix}/{asset.id}/file",
                thumbnail=f"{prefix}/{asset.id}/thumbnail",
            ),
        )


class AssetPage(BaseModel):
    """A page of assets. No total: it would be stale the moment it was read."""

    items: list[AssetRead]
    limit: int
    offset: int
    has_more: bool


#: One asset as the service answers with it, for the OpenAPI document
#: (FR-OPS-4). Taken from a real response of the demo corpus — a COCO picture
#: imported from a folder, with the tags the dataset's own annotations gave it
#: and the provenance the sidecar carried — so a reader sees the shape and the
#: kind of values an answer really has.
ASSET_READ_EXAMPLE: dict[str, Any] = {
    "id": "8e5567c3-22a2-4dd7-a625-61e07a03a46f",
    "created_at": "2026-09-26T18:35:22.564927Z",
    "content_type": "image/jpeg",
    "width": 426,
    "height": 640,
    "size_bytes": 110761,
    "sha256": "cecec146af7564d8229b996b99d25289924c039bf41475b0c533909699b39351",
    "original_filename": "000000096493.jpg",
    "source": "folder",
    "tags": ["couch", "person", "remote"],
    "meta": {
        "dataset": "coco-val2017",
        "licence": "http://creativecommons.org/licenses/by/2.0/",
        "dataset_id": "96493",
        "source_url": "http://farm4.staticflickr.com/3226/3076742158_8615337d86_z.jpg",
        "source_path": "96493/000000096493.jpg",
    },
    "index_status": {"clip-vit-l14": "done", "dinov2-large": "done"},
    "links": {
        "file": "/api/v1/assets/8e5567c3-22a2-4dd7-a625-61e07a03a46f/file",
        "thumbnail": "/api/v1/assets/8e5567c3-22a2-4dd7-a625-61e07a03a46f/thumbnail",
    },
}

#: A page of them. `has_more` is true here because the corpus it came from holds
#: sixty and the page asked for one.
ASSET_PAGE_EXAMPLE: dict[str, Any] = {
    "items": [ASSET_READ_EXAMPLE],
    "limit": 1,
    "offset": 0,
    "has_more": True,
}


class AssetPatch(BaseModel):
    """What an edit may change.

    An omitted field and an explicit null are different answers, and the
    difference is read from the fields the request actually carried rather than
    from a sentinel value — so `meta: null` clears the metadata while leaving
    the tags alone.
    """

    tags: list[str] | None = Field(default=None, description="Replaces every tag when given.")
    meta: dict[str, Any] | None = Field(default=None, description="Null clears the metadata.")

    def gives(self, field: str) -> bool:
        return field in self.model_fields_set


class DuplicateAssetProblem(ProblemDetails):
    """The 409 of an upload whose bytes are already stored."""

    existing_asset_id: UUID
