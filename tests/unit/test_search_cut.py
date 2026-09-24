"""Where a page is cut from the candidates, and what a threshold removes.

All three steps — the offset, the page, the threshold — were in the SQL until
change 12 needed the count of candidates *before* them. What they do did not
change, and this is where that is held: the same facts change 8 asserted against
a database, now asserted exactly and without one.
"""

from uuid import UUID, uuid4

import pytest

from app.domain import NeighbourHit
from app.services.search import cut, was_cut_short


def ranking(*distances: float) -> list[NeighbourHit]:
    return [NeighbourHit(asset_id=uuid4(), distance=distance) for distance in distances]


def ids(hits: list[NeighbourHit]) -> list[UUID]:
    return [hit.asset_id for hit in hits]


# --- the page ------------------------------------------------------------------


def test_a_page_is_the_nearest_candidates() -> None:
    candidates = ranking(0.0, 0.4, 1.0)

    page, has_more = cut(candidates, offset=0, limit=2, max_distance=None)

    assert ids(page) == ids(candidates[:2])
    assert has_more is True, "the third candidate is the row beyond the page"


def test_the_last_page_says_nothing_follows_it() -> None:
    candidates = ranking(0.0, 0.4, 1.0)

    page, has_more = cut(candidates, offset=0, limit=3, max_distance=None)

    assert ids(page) == ids(candidates)
    assert has_more is False


def test_an_offset_returns_the_tail_of_the_same_ranking() -> None:
    candidates = ranking(0.0, 0.4, 1.0)

    page, has_more = cut(candidates, offset=1, limit=3, max_distance=None)

    assert ids(page) == ids(candidates[1:])
    assert has_more is False


def test_an_offset_past_the_end_is_an_empty_page() -> None:
    page, has_more = cut(ranking(0.0, 0.4, 1.0), offset=10, limit=3, max_distance=None)

    assert page == []
    assert has_more is False


# --- the threshold --------------------------------------------------------------


def test_a_threshold_drops_results_without_refilling() -> None:
    """It applies to the page the search was asked for: the third candidate is
    not pulled up to replace the one that was dropped."""
    candidates = ranking(0.0, 0.4, 1.0)

    page, has_more = cut(candidates, offset=0, limit=2, max_distance=0.2)

    assert ids(page) == ids(candidates[:1])
    assert has_more is False


def test_a_threshold_that_nothing_reaches_is_an_empty_page() -> None:
    page, has_more = cut(ranking(0.0, 0.4, 1.0), offset=0, limit=3, max_distance=-0.5)

    assert page == []
    assert has_more is False


def test_a_threshold_that_keeps_a_full_page_still_says_more_exist() -> None:
    candidates = ranking(0.0, 0.1, 0.2, 0.3)

    page, has_more = cut(candidates, offset=0, limit=2, max_distance=0.25)

    assert ids(page) == ids(candidates[:2])
    assert has_more is True, "the third candidate passes it too"


def test_an_offset_and_a_threshold_together() -> None:
    candidates = ranking(0.0, 0.4, 1.0)

    page, has_more = cut(candidates, offset=1, limit=2, max_distance=0.5)

    assert ids(page) == ids(candidates[1:2]), "the first is skipped, the third is too far"
    assert has_more is False


def test_the_row_beyond_the_page_is_read_after_the_threshold_not_before() -> None:
    """A row the threshold removes has only further rows after it, so `has_more`
    stays exact: change 8's rule, kept by the same arithmetic one layer up."""
    candidates = ranking(0.0, 0.1, 5.0)

    page, has_more = cut(candidates, offset=0, limit=2, max_distance=1.0)

    assert len(page) == 2
    assert has_more is False


# --- was the scan cut short? -----------------------------------------------------
#
# The six rows of design decision 3, one test each. `limit` is 20 throughout.


def test_everything_the_answer_needed_was_reached() -> None:
    assert was_cut_short(reached=25, needed=21, matching=0) is False


def test_exactly_the_page_reached_while_more_exist() -> None:
    """The case a full page hides: 20 found, 21 needed, more in the store."""
    assert was_cut_short(reached=20, needed=21, matching=21) is True


def test_exactly_the_page_reached_and_that_is_all_there_is() -> None:
    assert was_cut_short(reached=20, needed=21, matching=20) is False


def test_nothing_reached_past_a_deep_offset_while_matches_exist() -> None:
    """offset 50, the scan finds 10 of 40 and stops: the page is empty, and the
    answer must still say the scan was cut short."""
    assert was_cut_short(reached=10, needed=71, matching=11) is True


def test_a_threshold_emptying_a_page_is_not_a_cut_short_scan() -> None:
    """The scan reached everything the answer needed; what the threshold did
    afterwards is not the search failing to find anything."""
    assert was_cut_short(reached=25, needed=21, matching=0) is False


def test_an_asset_search_that_reached_its_lookahead() -> None:
    """`/similar`, limit 20: 21 neighbours after the exclusion is everything the
    answer needs, and the question is never asked."""
    assert was_cut_short(reached=21, needed=21, matching=0) is False


@pytest.mark.parametrize(
    ("reached", "needed", "matching"),
    [(10, 71, 10), (0, 21, 0), (5, 21, 5)],
    ids=["deep offset, exhausted", "empty store", "short store"],
)
def test_an_exhausted_ranking_is_never_reported_as_cut_short(
    reached: int, needed: int, matching: int
) -> None:
    assert was_cut_short(reached=reached, needed=needed, matching=matching) is False
