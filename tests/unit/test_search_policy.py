"""What a search decides before it touches the store.

The arithmetic of a score, how hard the index is asked to look, and which pages
are refused outright — none of it needs a database, and all of it is easy to
get subtly wrong.
"""

import pytest

from app.core.settings import Settings
from app.services.search import (
    MAX_SEARCH_DEPTH,
    QUERY_MAX_LENGTH,
    PageTooDeepError,
    check_depth,
    effort_for,
    score_of,
)
from tests.conftest import UNREACHABLE_DATABASE_URL


def settings(**overrides: object) -> Settings:
    return Settings(  # type: ignore[arg-type]
        _env_file=None, database_url=UNREACHABLE_DATABASE_URL, **overrides
    )


@pytest.mark.parametrize(
    ("distance", "score"),
    [(0.0, 1.0), (1.0, 0.0), (2.0, -1.0), (0.4, 0.6)],
    ids=["identical", "orthogonal", "opposite", "near"],
)
def test_a_score_is_the_similarity_behind_the_distance(distance: float, score: float) -> None:
    assert score_of(distance) == pytest.approx(score)


def test_the_effort_is_never_below_the_configured_one() -> None:
    assert effort_for(settings=settings(), limit=5, offset=0) == 40


def test_the_effort_covers_the_page_and_the_row_beyond_it() -> None:
    """The row beyond the page is what says whether more exist, so the index
    has to be looking far enough to find it."""
    assert effort_for(settings=settings(), limit=100, offset=100) == 201


def test_the_effort_never_exceeds_what_pgvector_accepts() -> None:
    at_the_bound = effort_for(settings=settings(), limit=100, offset=900)

    assert at_the_bound == MAX_SEARCH_DEPTH, "1000 + 1 would be refused by the index"


def test_a_configured_effort_above_the_page_wins() -> None:
    assert effort_for(settings=settings(hnsw_ef_search=200), limit=10, offset=0) == 200


def test_a_page_within_the_depth_is_allowed() -> None:
    check_depth(limit=100, offset=900)  # exactly at the bound


def test_a_page_one_item_too_deep_is_refused() -> None:
    with pytest.raises(PageTooDeepError, match=str(MAX_SEARCH_DEPTH)):
        check_depth(limit=101, offset=900)


def test_the_query_bound_is_the_one_the_requirements_fix() -> None:
    assert QUERY_MAX_LENGTH == 256
