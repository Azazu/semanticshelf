"""The measurement's arithmetic, and the rules that choose what it measures.

`scripts/multilingual_benchmark.py` decides what ADR-005 says and therefore
which languages the service claims, so the parts of it that are not a database
are checked here: what recall and agreement mean, which concepts are eligible,
and each rule that makes a run report nothing rather than publish a number it
cannot stand behind.
"""

import numpy as np
import pytest

from tests.scripts import script_module

benchmark = script_module("multilingual_benchmark")


def corpus_of(tagged: dict[str, list[str]], *, assets: int = 40) -> object:
    """A corpus with no vectors: the selection rules never look at them."""
    ids = [f"asset-{number}" for number in range(assets)]
    return benchmark.Corpus(
        ids=ids,
        vectors=np.zeros((assets, 4), dtype=np.float32),
        tagged={tag: frozenset(members) for tag, members in tagged.items()},
    )


# --- what the two metrics mean -------------------------------------------------


def test_recall_is_how_much_of_what_carries_the_tag_reached_the_page() -> None:
    relevant = frozenset({"a", "b", "c", "d"})

    assert benchmark.recall_at(["a", "b", "x", "y"], relevant) == 0.5
    assert benchmark.recall_at(["a", "b", "c", "d"], relevant) == 1.0
    assert benchmark.recall_at(["x", "y"], relevant) == 0.0


def test_recall_of_a_concept_nothing_carries_is_zero_rather_than_undefined() -> None:
    # It cannot happen through the selection rules, and a division by zero here
    # would be a crash in the middle of a published measurement.
    assert benchmark.recall_at(["a"], frozenset()) == 0.0


def test_agreement_is_how_much_of_the_english_page_came_back() -> None:
    english = ["a", "b", "c", "d"]

    assert benchmark.agreement_at(["a", "b", "c", "d"], english) == 1.0
    assert benchmark.agreement_at(["a", "b", "x", "y"], english) == 0.5
    assert benchmark.agreement_at([], english) == 0.0
    assert benchmark.agreement_at(["a"], []) == 0.0


# --- which concepts may be asked about -----------------------------------------


def test_a_tag_carried_by_too_few_assets_is_not_asked_about() -> None:
    """One picture would decide the score for the whole concept."""
    corpus = corpus_of({"zebra": ["a", "b"]})  # MIN_ASSETS is 3

    assert benchmark.eligible(corpus) == []


def test_a_tag_carried_by_too_many_assets_is_not_asked_about() -> None:
    """Recall at ten cannot reach 1 when eleven pictures carry the tag."""
    corpus = corpus_of({"zebra": [f"a{n}" for n in range(11)]})  # MAX_ASSETS is 10

    assert benchmark.eligible(corpus) == []


def test_a_tag_within_the_bounds_is_asked_about() -> None:
    corpus = corpus_of({"zebra": ["a", "b", "c"], "elephant": [f"e{n}" for n in range(10)]})

    assert sorted(benchmark.eligible(corpus)) == ["elephant", "zebra"]


def test_a_tag_the_measurement_has_no_words_for_is_not_asked_about() -> None:
    """Ground truth is the corpus, but the question has to be askable."""
    corpus = corpus_of({"a-tag-nobody-translated": ["a", "b", "c"]})

    assert benchmark.eligible(corpus) == []


def test_every_concept_carries_every_language_it_claims() -> None:
    languages = {language for phrases in benchmark.CONCEPTS.values() for language in phrases}

    for concept, phrases in benchmark.CONCEPTS.items():
        assert set(phrases) == languages, f"{concept} is missing a language"
        assert all(phrase.strip() for phrase in phrases.values()), concept


# --- what makes a language claimed ---------------------------------------------


def measured(recall: float, *, language: str = "ru") -> object:
    return benchmark.Measured(
        language=language,
        asked_by="mclip-xlmr-l14",
        recall=recall,
        worst=("apple", 0.0),
        agreement=0.9,
    )


def test_a_language_clears_both_bounds_or_neither_counts() -> None:
    baseline = measured(0.8, language="en")

    assert benchmark.claimed(measured(0.8), baseline)
    # Above the absolute floor, but too far below the baseline.
    assert not benchmark.claimed(measured(0.6), baseline)
    # Close to the baseline, but the baseline is barely above chance itself.
    assert not benchmark.claimed(measured(0.4), measured(0.45, language="en"))


def test_a_baseline_of_zero_cannot_make_a_useless_encoder_pass() -> None:
    """The defect the relative bound had on its own, kept as a test."""
    nothing_works = measured(0.0, language="en")

    assert not benchmark.claimed(measured(0.0), nothing_works)


@pytest.mark.parametrize("recall", [0.0, 0.49])
def test_nothing_below_the_absolute_floor_is_claimed(recall: float) -> None:
    assert not benchmark.claimed(measured(recall), measured(0.0, language="en"))


# --- the agreement of a row with itself ----------------------------------------


def test_the_encoder_asked_in_english_is_compared_with_the_baseline() -> None:
    """Not with its own page, which would make agreement 1.000 by construction.

    This is the defect the first version of the script had, and the reason
    `measure` takes the baseline rather than looking it up by language.
    """
    corpus = corpus_of({"zebra": ["a", "b", "c"]})
    baseline_pages = {"zebra": ["a", "b", "c"]}
    encoder_pages = {"zebra": ["a", "x", "y"]}

    row = benchmark.measure(corpus, ["zebra"], encoder_pages, baseline_pages, "en", "mclip")

    assert row.agreement == pytest.approx(1 / 3)
    assert row.recall == pytest.approx(1 / 3)


# --- when the run refuses to publish anything ----------------------------------


def test_a_corpus_with_too_few_answerable_concepts_measures_nothing() -> None:
    """Twenty is the floor; below it the numbers are about this corpus's tags."""
    assert not benchmark.enough_concepts([f"concept-{n}" for n in range(19)])
    assert benchmark.enough_concepts([f"concept-{n}" for n in range(20)])


def test_a_baseline_that_cannot_answer_the_set_stops_the_run() -> None:
    """The service's own model is the sanity check on the concept set."""
    assert not benchmark.usable_baseline(measured(0.49, language="en"))
    assert benchmark.usable_baseline(measured(0.5, language="en"))
