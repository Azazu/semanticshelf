"""What a search answers with.

The item is the asset representation every other endpoint returns, plus the one
number this endpoint adds. The envelope says which model ranked the results,
because a score means nothing without it, and whether the query had to be cut,
because an answer to a shortened question should say so.
"""

from typing import Any

from pydantic import BaseModel, Field

from app.domain import DINOV2_LARGE
from app.schemas.assets import AssetRead

#: The page's bounds, so that paging feels the same everywhere. Here rather
#: than in the router, because one of the two searches takes them as form
#: fields and validates them with the model below.
DEFAULT_LIMIT = 20
MAX_LIMIT = 100


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
    scan_limited: bool = Field(
        default=False,
        description=(
            "True when the search stopped at the bound on how far it may look rather than at "
            "the end of the ranking: there are more results matching the narrowing, and this "
            "page is not the whole answer. Only a narrowed search can set it — narrow the "
            "query further, or ask for a smaller page."
        ),
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
    "scan_limited": False,
}


class ImageSearchQuery(BaseModel):
    """The page fields of a search whose query is an uploaded picture.

    They arrive as form fields beside the file, which is why they are validated
    by a model rather than by query parameters: a form field is a string, and
    the bounds have to hold all the same. The refusal a client sees is the
    framework's usual 422 problem details, with the field that was wrong.
    """

    limit: int = Field(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)
    offset: int = Field(default=0, ge=0)
    min_score: float | None = Field(default=None, ge=-1.0, le=1.0)
    model: str = Field(
        default=DINOV2_LARGE,
        description="Which model answers. It must be one this build runs, and one that takes "
        "pictures.",
    )
    #: Carried as written and parsed afterwards, with the `meta.<key>` fields of
    #: the same form: a narrowing is refused by its own problem type, naming the
    #: value that was wrong, rather than as a field of the wrong shape.
    tags_all: str | None = None
    tags_any: str | None = None
