"""The measurement's arithmetic, and the corpus it measures over.

`scripts/index_benchmark.py` decides what ADR-002 says, so the parts of it that
are not a database — what recall means, what p95 means, and whether the corpus
has neighbours to find at all — are checked here, without one.
"""

from uuid import UUID, uuid4

import numpy as np
import pytest

from tests.scripts import script_module

benchmark = script_module("index_benchmark")


# --- recall ----------------------------------------------------------------------


def identifiers(count: int) -> list[UUID]:
    return [uuid4() for _ in range(count)]


def test_an_index_that_found_the_ranking_scores_one() -> None:
    truth = identifiers(10)
    assert benchmark.recall_at(truth, truth) == 1.0


def test_an_index_that_found_none_of_it_scores_zero() -> None:
    assert benchmark.recall_at(identifiers(10), identifiers(10)) == 0.0


def test_half_of_the_ranking_is_half_the_score() -> None:
    truth = identifiers(10)
    found = truth[:5] + identifiers(5)
    assert benchmark.recall_at(found, truth) == 0.5


def test_order_within_the_answer_does_not_change_the_score() -> None:
    truth = identifiers(10)
    assert benchmark.recall_at(list(reversed(truth)), truth) == 1.0


def test_another_asset_at_the_same_distance_is_still_a_miss() -> None:
    """The conservative reading, and the one a user would recognise: a result
    that is as near as the true neighbour is not that neighbour."""
    truth = identifiers(10)
    substitute = uuid4()
    assert benchmark.recall_at(truth[:9] + [substitute], truth) == 0.9


def test_a_wider_answer_is_scored_against_the_ranking_it_was_given() -> None:
    truth = identifiers(10)
    assert benchmark.recall_at(truth + identifiers(11), truth) == 1.0


def test_recall_against_nothing_is_refused() -> None:
    with pytest.raises(ValueError):
        benchmark.recall_at(identifiers(3), [])


# --- the percentile ---------------------------------------------------------------


def test_p95_is_the_nearest_rank_sample() -> None:
    # Twenty samples: ceil(0.95 × 20) = 19, the nineteenth smallest.
    samples = [float(value) for value in range(1, 21)]
    assert benchmark.percentile(samples, 0.95) == 19.0


def test_p95_of_a_sample_count_that_does_not_divide_evenly() -> None:
    # Fifty samples: ceil(0.95 × 50) = 48.
    samples = [float(value) for value in range(1, 51)]
    assert benchmark.percentile(samples, 0.95) == 48.0


def test_p95_of_one_sample_is_that_sample() -> None:
    assert benchmark.percentile([4.2], 0.95) == 4.2


def test_the_percentile_does_not_depend_on_the_order_it_was_given() -> None:
    samples = [float(value) for value in range(1, 21)]
    assert benchmark.percentile(list(reversed(samples)), 0.95) == 19.0


def test_a_percentile_of_nothing_is_refused() -> None:
    with pytest.raises(ValueError):
        benchmark.percentile([], 0.95)


# --- the corpus -------------------------------------------------------------------


def test_every_vector_is_unit_length() -> None:
    """Cosine on L2-normalised rows is what the service stores and compares."""
    stored, queries = benchmark.corpus_of(stored=200, queries=10, dim=768, seed=7)
    for vectors in (stored, queries):
        assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=1e-5)


def test_the_corpus_has_neighbours_to_find() -> None:
    """A uniform sample of a 768-dimensional sphere has none — the tenth nearest
    is barely nearer than the thousandth — and recall over it would measure how
    an index broke a near-tie rather than whether it found anything."""
    stored, queries = benchmark.corpus_of(stored=1000, queries=5, dim=768, seed=7)
    for query in queries:
        distances = np.sort(1.0 - stored @ query)
        assert distances[9] < distances[99] / 2, "the tenth nearest is not a near-tie"


def test_the_same_seed_gives_the_same_corpus() -> None:
    first = benchmark.corpus_of(stored=100, queries=5, dim=768, seed=7)
    again = benchmark.corpus_of(stored=100, queries=5, dim=768, seed=7)
    other = benchmark.corpus_of(stored=100, queries=5, dim=768, seed=8)
    assert np.array_equal(first[0], again[0]) and np.array_equal(first[1], again[1])
    assert not np.array_equal(first[0], other[0])


def test_a_query_is_never_one_of_the_stored_vectors() -> None:
    """A query that is already stored has itself as its nearest neighbour, which
    every index finds and which measures nothing."""
    stored, queries = benchmark.corpus_of(stored=500, queries=20, dim=768, seed=7)
    for query in queries:
        assert not np.any(np.all(np.isclose(stored, query), axis=1))


def test_each_width_gets_its_own_vectors() -> None:
    narrow, _ = benchmark.corpus_of(stored=50, queries=2, dim=768, seed=7)
    wide, _ = benchmark.corpus_of(stored=50, queries=2, dim=1024, seed=7)
    assert narrow.shape == (50, 768)
    assert wide.shape == (50, 1024)


def test_a_vector_is_written_as_pgvector_reads_it() -> None:
    written = benchmark.literal(np.array([0.5, -0.25, 0.125], dtype=np.float32))
    assert written == "[0.5,-0.25,0.125]"
