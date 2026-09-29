"""The arithmetic ADR-006 rests on, and every value it refuses to divide by.

`scripts/style_benchmark.py` decides whether this project writes a migration
for a third model key, so the parts of it that are not a model are checked here
on hand-made vectors: what the deciding preference means, what the diagnostic
ratio means and when it has no value, and the bound — including the boundary it
sits exactly on.
"""

from pathlib import Path

import numpy as np
import pytest

from app.domain import EMBEDDING_MODELS
from tests.scripts import script_module

benchmark = script_module("style_benchmark")
style_corpus = benchmark.style_corpus
Label = style_corpus.Label

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "style_benchmark.py"


def corpus(pictures: int, looks: int) -> list[object]:
    """Labels for a `pictures × looks` corpus, in the order the stream makes."""
    names = ["plain", "grayscale", "posterised", "edges", "painterly", "sepia"][:looks]
    return [Label(picture=p, look=look) for p in range(pictures) for look in names]


def directions(labels: list[object], axis: str, width: int = 8) -> np.ndarray:
    """Unit vectors that depend on one side of a label and nothing else.

    `axis="look"` builds a model that sees only the look: two images sharing a
    look are the same vector, and one photograph under two looks is orthogonal
    to itself. `axis="picture"` is its mirror.
    """
    keys = sorted({getattr(label, axis) for label in labels})
    rows = np.zeros((len(labels), max(width, len(keys))), dtype=np.float32)
    for index, label in enumerate(labels):
        rows[index, keys.index(getattr(label, axis))] = 1.0
    return rows


# --- the deciding number -------------------------------------------------------


def test_a_model_that_sees_only_the_look_prefers_it_every_time() -> None:
    labels = corpus(pictures=4, looks=3)

    assert benchmark.preference(directions(labels, "look"), labels) == 1.0


def test_a_model_that_sees_only_the_subject_never_prefers_the_look() -> None:
    labels = corpus(pictures=4, looks=3)

    assert benchmark.preference(directions(labels, "picture"), labels) == 0.0


def test_a_model_that_cannot_tell_them_apart_sits_exactly_at_indifference() -> None:
    """Every comparison is a tie, and a tie counts a half — the alternative is
    to call it a win for one side, which would be an opinion."""
    labels = corpus(pictures=4, looks=3)
    identical = np.tile(np.array([[1.0, 0.0, 0.0]], dtype=np.float32), (len(labels), 1))

    assert benchmark.preference(identical, labels) == 0.5


def test_the_per_look_breakdown_restricts_the_anchors_to_that_look() -> None:
    """One look carries the average and the other works against it.

    Every `plain` image is the same vector, so its look-mates sit at 1 while
    its own photograph under the other look sits at 0.9 — the look wins from a
    `plain` anchor. Seen from a `grayscale` anchor the same two numbers are
    0.81 and 0.9, and the look loses. One corpus, one model, two rows that
    disagree: which is what a breakdown is for.
    """
    labels = corpus(pictures=3, looks=2)
    rows = np.zeros((len(labels), 8), dtype=np.float32)
    for index, label in enumerate(labels):
        if label.look == "plain":
            rows[index, 0] = 1.0
        else:
            rows[index, 0] = 0.9
            rows[index, 1 + label.picture] = float(np.sqrt(1 - 0.81))

    assert benchmark.preference(rows, labels, look="plain") == 1.0
    assert benchmark.preference(rows, labels, look="grayscale") == 0.0
    assert benchmark.preference(rows, labels) == 0.5


def test_a_corpus_of_one_look_forms_no_triple_and_is_refused() -> None:
    """No photograph under a second look, so there is nothing to compare a
    look-mate against; a number computed from nothing must not be printed."""
    labels = corpus(pictures=6, looks=1)

    with pytest.raises(benchmark.NoTriplesError):
        benchmark.preference(directions(labels, "picture"), labels)


def test_a_corpus_of_one_photograph_forms_no_triple_and_is_refused() -> None:
    labels = corpus(pictures=1, looks=6)

    with pytest.raises(benchmark.NoTriplesError):
        benchmark.preference(directions(labels, "look"), labels)


def test_the_number_of_triples_is_what_the_corpus_shape_says() -> None:
    """Every image is an anchor, with `pictures - 1` look-mates and
    `looks - 1` picture-mates."""
    labels = corpus(pictures=4, looks=3)

    assert benchmark.count_triples(labels) == 4 * 3 * (4 - 1) * (3 - 1)


# --- the diagnostic, and where it has no value ---------------------------------


def test_the_two_averages_are_the_two_sides_of_the_comparison() -> None:
    labels = corpus(pictures=3, looks=2)

    measured = benchmark.averages(directions(labels, "look"), labels)

    assert measured.same_look == pytest.approx(1.0)
    assert measured.same_picture == pytest.approx(0.0)
    assert (measured.look_pairs, measured.picture_pairs) == (6, 3)


def test_a_side_with_no_pairs_at_all_has_no_average() -> None:
    labels = corpus(pictures=1, looks=4)

    measured = benchmark.averages(directions(labels, "look"), labels)

    assert measured.same_look is None
    assert measured.look_pairs == 0


def test_a_zero_denominator_is_undefined_rather_than_a_division() -> None:
    measured = benchmark.Averages(same_look=0.4, same_picture=0.0, look_pairs=6, picture_pairs=3)

    assert measured.ratio is None


def test_a_negative_denominator_is_undefined_rather_than_a_reversed_ordering() -> None:
    """Through a negative denominator the ratio changes sign, so a model that
    ranks the subject first can outscore one that ranks the look first."""
    measured = benchmark.Averages(same_look=0.4, same_picture=-0.2, look_pairs=6, picture_pairs=3)

    assert measured.ratio is None


def test_a_missing_average_leaves_the_ratio_undefined() -> None:
    assert benchmark.Averages(0.4, None, 6, 0).ratio is None
    assert benchmark.Averages(None, 0.4, 0, 3).ratio is None


def test_a_positive_denominator_is_the_plain_ratio() -> None:
    assert benchmark.Averages(0.4, 0.8, 6, 3).ratio == pytest.approx(0.5)


def test_undefined_is_printed_as_a_word_not_as_a_number() -> None:
    assert benchmark.shown(None) == "undefined"
    assert benchmark.shown(0.4567) == "0.457"


# --- the bound -----------------------------------------------------------------


def test_the_bound_is_half_the_distance_the_incumbent_still_has_to_go() -> None:
    assert benchmark.bound([0.0]) == 0.5
    assert benchmark.bound([0.2]) == pytest.approx(0.6)
    assert benchmark.bound([0.9]) == pytest.approx(0.95)


def test_the_bound_is_taken_against_the_best_incumbent_not_the_first() -> None:
    """A candidate that beats one stored key and duplicates another has not
    answered the question the measurement asks."""
    assert benchmark.bound([0.02, 0.60, 0.11]) == pytest.approx(0.8)


def test_a_candidate_short_of_the_bound_does_not_clear_it() -> None:
    assert benchmark.clears(0.79, [0.60]) is False


def test_a_candidate_exactly_on_the_bound_does_not_clear_it() -> None:
    """Strict: a tie does not buy a migration."""
    assert benchmark.clears(0.8, [0.60]) is False


def test_a_candidate_above_the_bound_clears_it() -> None:
    assert benchmark.clears(0.81, [0.60]) is True


def test_against_an_incumbent_at_zero_the_bound_is_indifference_itself() -> None:
    """The one point where the bound would coincide with 0.5, which is why the
    comparison is strict and why there is no second condition."""
    assert benchmark.bound([0.0]) == 0.5
    assert benchmark.clears(0.5, [0.0]) is False
    assert benchmark.clears(0.51, [0.0]) is True


def test_a_margin_over_nothing_is_refused() -> None:
    with pytest.raises(ValueError, match="margin"):
        benchmark.bound([])


# --- what gets measured --------------------------------------------------------


def test_the_measured_keys_are_the_ones_the_domain_declares() -> None:
    assert benchmark.incumbents() == tuple(sorted(EMBEDDING_MODELS))


def test_no_model_key_is_written_out_in_the_command() -> None:
    """The point of reading them from the domain: a key added to
    `EMBEDDING_MODELS` later appears in this measurement without anybody
    remembering to add it here."""
    source = SCRIPT.read_text(encoding="utf-8")

    assert [key for key in EMBEDDING_MODELS if key in source] == []


# --- what a reader needs to tell whether they have the same inputs -------------


def test_the_corpus_digest_is_over_the_names_and_the_bytes(tmp_path: Path) -> None:
    """ "The first hundred pictures of a folder" is not a corpus anyone else can
    obtain; the digest is what two runs compare to find out whether they
    measured the same pictures."""
    (tmp_path / "a.jpg").write_bytes(b"first")
    (tmp_path / "b.jpg").write_bytes(b"second")
    plan = style_corpus.Corpus(
        root=tmp_path, paths=style_corpus.photographs(tmp_path), looks=tuple(style_corpus.LOOKS)
    )

    before = benchmark.corpus_digest(plan)

    assert before == benchmark.corpus_digest(plan)
    (tmp_path / "b.jpg").write_bytes(b"second, edited")
    assert benchmark.corpus_digest(plan) != before


def test_the_digest_changes_when_a_picture_is_renamed(tmp_path: Path) -> None:
    (tmp_path / "a.jpg").write_bytes(b"first")
    plan = style_corpus.Corpus(
        root=tmp_path, paths=style_corpus.photographs(tmp_path), looks=tuple(style_corpus.LOOKS)
    )
    before = benchmark.corpus_digest(plan)

    (tmp_path / "a.jpg").rename(tmp_path / "z.jpg")
    renamed = style_corpus.Corpus(
        root=tmp_path, paths=style_corpus.photographs(tmp_path), looks=tuple(style_corpus.LOOKS)
    )

    assert benchmark.corpus_digest(renamed) != before


def test_every_configured_checkpoint_is_reported(tmp_path: Path) -> None:
    """Read from the settings fields rather than a list, for the same reason the
    measured keys are read from `app.domain`."""
    from app.core.settings import Settings

    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://127.0.0.1:1/nowhere",
        model_cache=tmp_path,
    )

    rows = benchmark.checkpoints(settings)
    fields = [field for field, _, _ in rows]

    assert fields == sorted(f for f in type(settings).model_fields if f.endswith("_model_name"))
    assert fields, "no checkpoint setting was found to report"


def test_a_checkpoint_the_cache_does_not_hold_is_reported_as_unresolved(tmp_path: Path) -> None:
    """Reported, never claimed: only the candidate is pinned by this repository,
    and a name that resolved to nothing must not read as a fixed identity."""
    from app.core.settings import Settings

    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://127.0.0.1:1/nowhere",
        model_cache=tmp_path / "empty",
    )

    assert all(revision == "unresolved" for _, _, revision in benchmark.checkpoints(settings))


# --- the command path, not just the functions it calls -------------------------


def uniform_picture() -> object:
    """A photograph every look flattens to one colour, so nothing survives."""
    from PIL import Image

    return Image.new("RGB", (32, 32), (128, 128, 128))


def test_a_wholly_refused_corpus_is_refused_in_words_not_in_a_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Twenty photographs pass the plan's bound and none of them survives its
    looks. The functions each behave, and the path between them used to raise
    `need at least one array to concatenate` before the refusal was reached."""
    from PIL import Image

    paths = tuple(tmp_path / f"{n}.jpg" for n in range(style_corpus.MIN_PICTURES))
    monkeypatch.setattr(style_corpus, "photographs", lambda folder: paths)
    monkeypatch.setattr(Image, "open", lambda path: uniform_picture())

    class Nothing:
        """An embedder the run must never reach."""

        def embed_images(self, images: object) -> object:  # pragma: no cover - not reached
            raise AssertionError("a refused corpus must not be embedded")

    monkeypatch.setattr(
        benchmark.style_candidate.StyleCandidate, "load", lambda settings: Nothing()
    )
    monkeypatch.setattr(
        benchmark, "FACTORIES", {key: lambda s: Nothing() for key in benchmark.incumbents()}
    )
    configured = benchmark.Settings(  # type: ignore[call-arg]
        _env_file=None,
        database_url="postgresql+asyncpg://127.0.0.1:1/nowhere",
        model_cache=tmp_path / "models",
    )
    monkeypatch.setattr(benchmark, "Settings", lambda: configured)
    monkeypatch.setattr("sys.argv", ["style_benchmark.py", "--folder", str(tmp_path)])

    code = benchmark.main()

    assert code == 2
    printed = capsys.readouterr().out
    assert "nothing measured" in printed
    # The words alone are not the path: a folder with no photographs at all
    # refuses with the same opening and never reaches the embedding.
    assert "every look of every photograph was refused" in printed


# --- what the provenance table may and may not be read as ----------------------


def test_the_checkpoint_table_says_it_establishes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The rows look like provenance and are not: each adapter resolves its
    weights and its processor separately, without a revision."""
    from app.core.settings import Settings

    (tmp_path / "a.jpg").write_bytes(b"first")
    plan = style_corpus.Corpus(
        root=tmp_path, paths=style_corpus.photographs(tmp_path), looks=("plain", "grayscale")
    )
    labels = corpus(pictures=2, looks=2)
    vectors = directions(labels, "look")
    rows = [
        benchmark.score(name, vectors, labels) for name in ("csd-vit-l", *benchmark.incumbents())
    ]
    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://127.0.0.1:1/nowhere",
        model_cache=tmp_path / "models",
    )

    benchmark.report(plan, labels, rows, settings)
    printed = capsys.readouterr().out

    assert benchmark.PROVENANCE_CAVEAT in printed
    assert "diagnostic only" in benchmark.PROVENANCE_CAVEAT
    assert "establish neither matching inputs nor matching numbers" in benchmark.PROVENANCE_CAVEAT
