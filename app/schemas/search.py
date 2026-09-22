"""What a search answers with.

The item is the asset representation every other endpoint returns, plus the one
number this endpoint adds. The envelope says which model ranked the results,
because a score means nothing without it, and whether the query had to be cut,
because an answer to a shortened question should say so.
"""

from typing import Any

from pydantic import BaseModel, Field

from app.schemas.assets import AssetRead


class SearchHit(BaseModel):
    """One result: the asset, and how near it was to the query."""

    asset: AssetRead
    score: float = Field(
        description=(
            "Cosine similarity between the query and this asset's vector, in [-1, 1]. "
            "Larger is nearer. Comparable only within one model."
        )
    )


class SearchPage(BaseModel):
    """A page of a ranking. No total: with an approximate index and a threshold
    an exact count would cost a full scan, and would be stale when it arrived."""

    items: list[SearchHit]
    limit: int
    offset: int
    has_more: bool
    model: str = Field(
        description="The model whose vectors were ranked, and which embedded the query."
    )
    query_truncated: bool = Field(
        description="True when the model could not represent the whole query and cut it."
    )


#: What one answer looks like, for the OpenAPI document (FR-OPS-4). Taken from
#: the run recorded in `docs/how-to/searching.md`, so it is the shape and the
#: order of magnitude a caller actually gets rather than a round invention.
SEARCH_PAGE_EXAMPLE: dict[str, Any] = {
    "items": [
        {
            "score": 0.248,
            "asset": {
                "id": "e7a141b9-9cc3-4b9f-b0a3-2cd0e32a8705",
                "created_at": "2026-09-21T16:04:11.512883Z",
                "content_type": "image/png",
                "width": 512,
                "height": 512,
                "size_bytes": 2374,
                "sha256": "4d1f6e0a2b8c5d3e9f07a1b4c6d8e2f0a3b5c7d9e1f2a4b6c8d0e2f4a6b8c0d2",
                "original_filename": "red-field.png",
                "source": "folder",
                "tags": ["demo"],
                "meta": {},
                "index_status": {"clip-vit-l14": "done"},
                "links": {
                    "file": "/api/v1/assets/e7a141b9-9cc3-4b9f-b0a3-2cd0e32a8705/file",
                    "thumbnail": "/api/v1/assets/e7a141b9-9cc3-4b9f-b0a3-2cd0e32a8705/thumbnail",
                },
            },
        }
    ],
    "limit": 1,
    "offset": 0,
    "has_more": True,
    "model": "clip-vit-l14",
    "query_truncated": False,
}
