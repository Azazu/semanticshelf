"""What a search answers with.

The item is the asset representation every other endpoint returns, plus the one
number this endpoint adds. The envelope says which model ranked the results,
because a score means nothing without it, and whether the query had to be cut,
because an answer to a shortened question should say so.
"""

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
