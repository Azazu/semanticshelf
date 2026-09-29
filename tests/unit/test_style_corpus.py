"""The corpus rules, which decide what the published measurement is computed on.

`scripts/style_corpus.py` builds the ground truth ADR-006 rests on, so the
properties that make it a ground truth at all are checked here: that a look is a
pure function of the bytes, that it returns a picture of the same size, and that
each rule which makes a run measure nothing actually refuses.
"""

from pathlib import Path

import pytest
from PIL import Image
from PIL.Image import Image as Picture

from tests.scripts import script_module

corpus = script_module("style_corpus")


def photograph(*, size: tuple[int, int] = (64, 48), low: int = 0, high: int = 255) -> Picture:
    """A gradient over all three channels, between the two values given.

    `low` and `high` are what lets a test build a picture a look will flatten:
    a frame whose every channel sits between 200 and 255 posterises to one
    colour, while a frame over the whole range posterises to four.
    """
    picture = Image.new("RGB", size)
    width, height = size
    span = max(high - low, 0)
    pixels = picture.load()
    assert pixels is not None
    for x in range(width):
        for y in range(height):
            step = (x + y) / max(width + height - 2, 1)
            value = low + round(span * step)
            pixels[x, y] = (value, min(value + span // 3, high), min(value + span // 2, high))
    return picture


# --- a look is a pure function of the bytes ------------------------------------


@pytest.mark.parametrize("look", sorted(corpus.LOOKS))
def test_a_look_gives_the_same_bytes_every_time(look: str) -> None:
    """Determinism is not a nicety here: it is what lets the published command
    be re-run and produce the published numbers."""
    picture = photograph()

    first = corpus.LOOKS[look](picture)
    second = corpus.LOOKS[look](picture)

    assert first.tobytes() == second.tobytes()


@pytest.mark.parametrize("look", sorted(corpus.LOOKS))
def test_a_look_keeps_the_size_of_the_picture(look: str) -> None:
    picture = photograph(size=(37, 23))

    assert corpus.LOOKS[look](picture).size == (37, 23)


@pytest.mark.parametrize("look", sorted(corpus.LOOKS))
def test_a_look_answers_in_rgb(look: str) -> None:
    """Every model here takes three channels; a look that quietly returned one
    would be re-converted by the adapter and measured as something else."""
    assert corpus.LOOKS[look](photograph()).mode == "RGB"


# --- what the corpus refuses to measure ----------------------------------------


def test_a_look_that_flattens_a_picture_to_one_colour_is_refused() -> None:
    """A near-white frame posterises to a single value, and a picture that kept
    nothing of its subject cannot stand on either side of the comparison."""
    near_white = photograph(low=200, high=255)

    assert corpus.is_constant(corpus.LOOKS["posterised"](near_white))
    assert corpus.looked_at(near_white, "posterised") is None


def test_the_same_picture_is_still_measured_under_the_looks_that_keep_it() -> None:
    """The refusal is of one combination, not of the photograph."""
    near_white = photograph(low=200, high=255)

    assert corpus.looked_at(near_white, "plain") is not None
    assert corpus.looked_at(near_white, "edges") is not None


def test_a_picture_of_one_colour_is_refused_under_every_look() -> None:
    """`edges` is the one that would slip through a rule reading the whole
    picture: a 3x3 filter leaves the border, so the result is a uniform field
    inside the photograph's own frame."""
    flat = Image.new("RGB", (32, 32), (128, 128, 128))

    assert [look for look in corpus.LOOKS if corpus.looked_at(flat, look) is not None] == []


def test_a_gradient_is_refused_under_no_look() -> None:
    picture = photograph()

    assert [look for look in corpus.LOOKS if corpus.looked_at(picture, look) is None] == []


# --- the two bounds ------------------------------------------------------------


def test_too_few_photographs_is_refused(tmp_path: Path) -> None:
    small = corpus.Corpus(
        root=tmp_path,
        paths=tuple(tmp_path / f"{n}.jpg" for n in range(corpus.MIN_PICTURES - 1)),
        looks=tuple(corpus.LOOKS),
    )

    with pytest.raises(corpus.CorpusTooSmallError, match="photographs"):
        corpus.check_size(small)


def test_exactly_the_minimum_number_of_photographs_is_measured(tmp_path: Path) -> None:
    enough = corpus.Corpus(
        root=tmp_path,
        paths=tuple(tmp_path / f"{n}.jpg" for n in range(corpus.MIN_PICTURES)),
        looks=tuple(corpus.LOOKS),
    )

    corpus.check_size(enough)


def test_too_few_looks_is_refused(tmp_path: Path) -> None:
    narrow = corpus.Corpus(
        root=tmp_path,
        paths=tuple(tmp_path / f"{n}.jpg" for n in range(corpus.MIN_PICTURES)),
        looks=tuple(corpus.LOOKS)[: corpus.MIN_LOOKS - 1],
    )

    with pytest.raises(corpus.CorpusTooSmallError, match="looks"):
        corpus.check_size(narrow)


def test_the_published_set_of_looks_clears_the_bound() -> None:
    assert len(corpus.LOOKS) >= corpus.MIN_LOOKS


# --- the plan the benchmark walks ----------------------------------------------


def test_the_corpus_is_read_in_a_fixed_order(tmp_path: Path) -> None:
    """A re-run must measure the same corpus, so the folder's order is sorted
    rather than whatever the filesystem hands back."""
    for name in ("c.jpg", "a.jpg", "b.jpg"):
        photograph(size=(8, 8)).save(tmp_path / name)

    assert [path.name for path in corpus.photographs(tmp_path)] == ["a.jpg", "b.jpg", "c.jpg"]


def test_a_picture_in_a_directory_of_its_own_is_found(tmp_path: Path) -> None:
    """The demo corpus stores each photograph beside its sidecar in a directory
    named after it, so a walk that read one level would measure nothing."""
    for name in ("b", "a"):
        shard = tmp_path / name
        shard.mkdir()
        photograph(size=(8, 8)).save(shard / f"{name}.jpg")
        (shard / f"{name}.json").write_text("{}", encoding="utf-8")

    assert [path.name for path in corpus.photographs(tmp_path)] == ["a.jpg", "b.jpg"]


def test_only_pictures_are_read(tmp_path: Path) -> None:
    photograph(size=(8, 8)).save(tmp_path / "a.jpg")
    (tmp_path / "notes.txt").write_text("not a photograph", encoding="utf-8")

    assert [path.name for path in corpus.photographs(tmp_path)] == ["a.jpg"]


def test_every_look_of_every_photograph_is_streamed_with_its_label(tmp_path: Path) -> None:
    for name in ("a.jpg", "b.jpg"):
        photograph(size=(16, 16)).save(tmp_path / name)
    plan = corpus.Corpus(
        root=tmp_path, paths=corpus.photographs(tmp_path), looks=("plain", "grayscale")
    )

    labels = [label for label, _ in corpus.images(plan)]

    assert [(label.picture, label.look) for label in labels] == [
        (0, "plain"),
        (0, "grayscale"),
        (1, "plain"),
        (1, "grayscale"),
    ]


def test_what_the_corpus_holds_is_reported_after_the_refusals(tmp_path: Path) -> None:
    for name in ("a.jpg", "b.jpg"):
        photograph(size=(16, 16)).save(tmp_path / name)
    plan = corpus.Corpus(
        root=tmp_path, paths=corpus.photographs(tmp_path), looks=("plain", "grayscale")
    )

    pictures, looks = corpus.present([label for label, _ in corpus.images(plan)])

    assert (pictures, looks) == (2, ("plain", "grayscale"))


def test_a_batch_keeps_the_order_and_the_last_short_one(tmp_path: Path) -> None:
    for name in ("a.jpg", "b.jpg", "c.jpg"):
        photograph(size=(8, 8)).save(tmp_path / name)
    plan = corpus.Corpus(root=tmp_path, paths=corpus.photographs(tmp_path), looks=("plain",))

    batches = [labels for labels, _ in corpus.batched(corpus.images(plan), 2)]

    assert [[label.picture for label in labels] for labels in batches] == [[0, 1], [2]]


# --- the bounds applied to what survived, not to what was planned --------------


def test_a_corpus_whose_looks_were_refused_away_is_refused(tmp_path: Path) -> None:
    """Twenty planned photographs are not twenty measured ones: a plan that
    loses eighteen of them to the constant-picture rule leaves two, and a
    number computed from two photographs is exactly what the bound forbids."""
    labels = [corpus.Label(picture=n, look=look) for n in range(2) for look in corpus.LOOKS]

    with pytest.raises(corpus.CorpusTooSmallError, match="survived"):
        corpus.check_present(labels)


def test_a_corpus_that_lost_its_looks_is_refused() -> None:
    labels = [
        corpus.Label(picture=n, look=look)
        for n in range(corpus.MIN_PICTURES)
        for look in tuple(corpus.LOOKS)[: corpus.MIN_LOOKS - 1]
    ]

    with pytest.raises(corpus.CorpusTooSmallError, match="looks survived"):
        corpus.check_present(labels)


def test_a_corpus_refused_away_entirely_is_refused_cleanly() -> None:
    with pytest.raises(corpus.CorpusTooSmallError, match="nothing to measure"):
        corpus.check_present([])


def test_a_corpus_that_survived_intact_is_measured() -> None:
    labels = [
        corpus.Label(picture=n, look=look)
        for n in range(corpus.MIN_PICTURES)
        for look in corpus.LOOKS
    ]

    corpus.check_present(labels)
