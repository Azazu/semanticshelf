"""What a search decides before it touches the store.

The arithmetic of a score, how hard the index is asked to look, and which pages
are refused outright — none of it needs a database, and all of it is easy to
get subtly wrong.
"""

import pytest

from app.core.settings import Settings
from app.services.search import (
    MAX_PAGE_DEPTH,
    MAX_SEARCH_EFFORT,
    QUERY_MAX_LENGTH,
    InvalidQueryError,
    PageTooDeepError,
    check_depth,
    effort_for,
    normalised_query,
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
    at_the_bound = effort_for(settings=settings(), limit=100, offset=MAX_PAGE_DEPTH - 100)

    assert at_the_bound == MAX_SEARCH_EFFORT, "anything above it the index would refuse"


def test_the_deepest_page_the_service_answers_still_has_its_sentinel() -> None:
    """The one that ties the two bounds together: `has_more` is the row beyond
    the page, so the deepest allowed page must still leave the index a
    candidate to produce it with. Raise `MAX_PAGE_DEPTH` to the index's own
    ceiling and this fails — the page would need candidate 1001 of 1000.
    """
    limit, offset = 100, MAX_PAGE_DEPTH - 100

    check_depth(limit=limit, offset=offset)

    assert effort_for(settings=settings(), limit=limit, offset=offset) >= limit + offset + 1


def test_a_configured_effort_above_the_page_wins() -> None:
    assert effort_for(settings=settings(hnsw_ef_search=200), limit=10, offset=0) == 200


def test_a_page_within_the_depth_is_allowed() -> None:
    check_depth(limit=100, offset=MAX_PAGE_DEPTH - 100)  # exactly at the bound


def test_a_page_one_item_too_deep_is_refused() -> None:
    with pytest.raises(PageTooDeepError, match=str(MAX_PAGE_DEPTH)):
        check_depth(limit=101, offset=MAX_PAGE_DEPTH - 100)


def test_the_query_bound_is_the_one_the_requirements_fix() -> None:
    assert QUERY_MAX_LENGTH == 256


def test_a_query_is_used_trimmed() -> None:
    assert normalised_query("  a blue dragon\t\n") == "a blue dragon"


@pytest.mark.parametrize("raw", ["", "   ", "\t\n"], ids=["empty", "spaces", "whitespace"])
def test_a_query_with_nothing_in_it_is_refused(raw: str) -> None:
    with pytest.raises(InvalidQueryError, match="empty"):
        normalised_query(raw)


def test_the_bound_is_measured_after_trimming() -> None:
    """The padding is not the query. Measure the raw string instead — which is
    what a `max_length` on the parameter does — and this one is refused for a
    length it does not have.
    """
    padded = "  " + "d" * QUERY_MAX_LENGTH + "  "

    assert normalised_query(padded) == "d" * QUERY_MAX_LENGTH


def test_a_query_beyond_the_bound_after_trimming_is_refused() -> None:
    with pytest.raises(InvalidQueryError, match=str(QUERY_MAX_LENGTH)):
        normalised_query(" " + "d" * (QUERY_MAX_LENGTH + 1) + " ")
