"""What a search decides before it touches the store.

The arithmetic of a score, how hard the index is asked to look, and which pages
are refused outright — none of it needs a database, and all of it is easy to
get subtly wrong.
"""

import re
from typing import Any
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.core.settings import Settings
from app.domain import CLIP_VIT_L14, dimension_of
from app.repositories.embeddings import EmbeddingRepository
from app.services.search import (
    MAX_PAGE_DEPTH,
    MAX_PAGE_DEPTH_EXCLUDING,
    MAX_SEARCH_EFFORT,
    QUERY_MAX_LENGTH,
    InvalidQueryError,
    PageTooDeepError,
    check_depth,
    depth_bound,
    effort_for,
    normalised_query,
    rows_needed,
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


# --- a search that leaves an asset out of its own answer ----------------------


def test_leaving_a_row_out_costs_one_page_of_depth() -> None:
    assert MAX_PAGE_DEPTH_EXCLUDING == MAX_PAGE_DEPTH - 1 == depth_bound(excluded=1)


def test_the_effort_covers_the_page_the_sentinel_and_the_excluded_row() -> None:
    # Deep enough that the page decides rather than the configured floor.
    assert effort_for(settings=settings(), limit=100, offset=100, excluded=1) == 202


def test_the_deepest_excluding_page_still_has_both_rows_it_cannot_use() -> None:
    """The test that ties the excluding bound to the index's ceiling. Raise
    `MAX_PAGE_DEPTH_EXCLUDING` to the ordinary depth and this fails: the page
    would need candidate 1001 of the 1000 the index will produce, and
    `has_more` would become a guess at exactly the depth a client is most
    likely to be paging towards.
    """
    limit, offset = 100, MAX_PAGE_DEPTH_EXCLUDING - 100

    check_depth(limit=limit, offset=offset, excluded=1)
    effort = effort_for(settings=settings(), limit=limit, offset=offset, excluded=1)

    assert effort >= limit + offset + 2
    assert effort <= MAX_SEARCH_EFFORT


def test_every_accepted_excluding_page_is_within_the_effort_it_is_granted() -> None:
    """Not only the deepest one: the invariant is that the index is always
    asked for at least the page, the row beyond it and the excluded asset."""
    for limit, offset in [(1, 0), (20, 0), (100, 0), (1, MAX_PAGE_DEPTH_EXCLUDING - 1), (50, 948)]:
        check_depth(limit=limit, offset=offset, excluded=1)
        assert (
            effort_for(settings=settings(), limit=limit, offset=offset, excluded=1)
            >= limit + offset + 2
        ), (limit, offset)


def test_the_page_a_text_query_may_ask_for_is_one_too_deep_here() -> None:
    limit, offset = 100, MAX_PAGE_DEPTH - 100

    check_depth(limit=limit, offset=offset)  # allowed without an exclusion

    with pytest.raises(PageTooDeepError, match=str(MAX_PAGE_DEPTH_EXCLUDING)):
        check_depth(limit=limit, offset=offset, excluded=1)


# --- how many rows are asked for, and how many the answer needs -----------------
#
# Two numbers that differ by exactly the rows the page may not use, and change
# 12 made the difference matter: the scan's reach against what the answer needed
# is what says whether it was cut short (design decision 3). They are read here
# from the compiled statement and from the service's own rule, side by side,
# because a drift between them is silent in both directions — one extra row
# required makes every asset search pay for the bounded question, one too few
# makes `has_more` a guess.

QUERY_VECTOR = [0.0] * dimension_of(CLIP_VIT_L14)


def limits_of(statement: sa.Select[Any]) -> list[int]:
    """Every LIMIT the statement carries, innermost first: the window's, then
    the page's. Read from the SQL the database would be sent."""
    compiled = statement.compile(dialect=postgresql.dialect())
    names = re.findall(r"LIMIT %\((\w+)\)s", str(compiled))
    return [int(compiled.params[name]) for name in names]


def window_for(needed: int, *, excluding: bool) -> list[int]:
    repository = EmbeddingRepository(None)  # type: ignore[arg-type]
    return limits_of(
        repository.nearest_statement(
            model=CLIP_VIT_L14,
            vector=QUERY_VECTOR,
            limit=needed,
            exclude_asset_id=uuid4() if excluding else None,
        )
    )


def test_the_answer_needs_the_offset_the_page_and_the_row_beyond_it() -> None:
    assert rows_needed(limit=20, offset=0) == 21
    assert rows_needed(limit=20, offset=50) == 71


def test_an_ordinary_search_asks_for_exactly_what_the_answer_needs() -> None:
    needed = rows_needed(limit=20, offset=50)

    assert window_for(needed, excluding=False) == [needed, needed], "window, then page"


def test_an_asset_search_asks_for_one_row_more_than_the_answer_needs() -> None:
    """The asset itself is dropped between the window and the page, so the
    window carries it and the answer never counts on it."""
    needed = rows_needed(limit=20, offset=50)
    window, page = window_for(needed, excluding=True)

    assert window == needed + 1
    assert page == needed


def test_the_exclusion_costs_nothing_to_what_the_answer_requires() -> None:
    """The one that fails if the extra row is ever moved into `rows_needed`:
    what an asset search needs is what any search of that shape needs."""
    assert rows_needed(limit=20, offset=0) == 21
    assert window_for(21, excluding=True)[1] == 21, "the page is unchanged by the exclusion"


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
