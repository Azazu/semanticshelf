"""The corpus this measurement needs and could not find.

A style corpus of paintings would be the natural thing to measure on, and this
project cannot have one: the licences that would let it re-encode a thumbnail
rule out the obvious sources (ADR-006, and the rule change 9 set). So the
corpus is **built** from the pictures already in the repository, by applying a
fixed set of deterministic looks to each of them.

That gives a ground truth nobody has to label: two images share a look because
the same function produced them, and share a subject because they came from the
same photograph. It also gives reproducibility for free — every look is a pure
function of the bytes, so a re-run of the benchmark rebuilds exactly the same
corpus without downloading anything.

**These are filters, not painters.** What the corpus can support is a statement
about separating *how a picture looks* from *what is in it*. It is not evidence
about artistic style, and ADR-006 says so in those words.

Two rules keep a run from publishing a number it cannot stand behind:

- a look that returns a **constant picture** for a photograph — one colour
  everywhere, which a hard posterisation of a near-white frame can produce —
  keeps no subject, so the pair it would form carries no ground truth. That one
  combination is dropped rather than measured;
- a corpus below `MIN_PICTURES` photographs or `MIN_LOOKS` looks is refused
  outright. Four pictures decide nothing, and the probe that four pictures
  supported is in the proposal, not in a published table.
"""

from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from PIL import Image, ImageFilter, ImageOps
from PIL.Image import Image as Picture

#: A look: one picture in, one picture of the same size out, no state between
#: calls and nothing read but the pixels it was given.
Look = Callable[[Picture], Picture]

#: Below either of these the run reports what it has and measures nothing.
MIN_PICTURES: Final = 20
MIN_LOOKS: Final = 4


def plain(picture: Picture) -> Picture:
    """The photograph itself, which is one of the looks and stays in: a style
    search is run against ordinary pictures, and leaving them out would measure
    a corpus nobody has."""
    return picture.convert("RGB")


def grayscale(picture: Picture) -> Picture:
    return ImageOps.grayscale(picture).convert("RGB")


def posterised(picture: Picture) -> Picture:
    return ImageOps.posterize(picture.convert("RGB"), 2)


def edges(picture: Picture) -> Picture:
    return ImageOps.invert(picture.convert("L").filter(ImageFilter.FIND_EDGES)).convert("RGB")


def painterly(picture: Picture) -> Picture:
    flattened = picture.convert("RGB").filter(ImageFilter.ModeFilter(9))
    return ImageOps.posterize(flattened.filter(ImageFilter.SMOOTH_MORE), 3)


def sepia(picture: Picture) -> Picture:
    return ImageOps.colorize(picture.convert("L"), "#2b1b0e", "#ffe7b3").convert("RGB")


#: The looks the published measurement uses, in the order the table prints them.
LOOKS: Final[Mapping[str, Look]] = {
    "plain": plain,
    "grayscale": grayscale,
    "posterised": posterised,
    "edges": edges,
    "painterly": painterly,
    "sepia": sepia,
}


class CorpusTooSmallError(RuntimeError):
    """A corpus that cannot carry the measurement asked of it."""


@dataclass(frozen=True, slots=True)
class Label:
    """Which photograph an image came from, and which look produced it."""

    picture: int
    look: str


@dataclass(frozen=True, slots=True)
class Corpus:
    """The plan of a corpus: the photographs and the looks applied to each.

    The images themselves are not held. A corpus of a hundred photographs under
    six looks is six hundred pictures, and the benchmark loads one model at a
    time over a stream of batches rather than keeping all of that and three
    models in memory at once.
    """

    root: Path
    paths: tuple[Path, ...]
    looks: tuple[str, ...]

    @property
    def size(self) -> int:
        """How many images the plan produces before any is refused."""
        return len(self.paths) * len(self.looks)


#: What counts as a photograph here. The demo corpus stores each picture in a
#: directory of its own beside a sidecar, so the walk is recursive.
SUFFIXES: Final = frozenset({".jpg", ".jpeg"})


def photographs(folder: Path) -> tuple[Path, ...]:
    """Every picture under a folder, in a fixed order so a re-run measures the
    same corpus. `rglob` does not promise an order, so the result is sorted."""
    found = [path for path in folder.rglob("*") if path.suffix.lower() in SUFFIXES]
    return tuple(sorted(found))


def corpus_of(folder: Path, *, limit: int | None = None) -> Corpus:
    """Plan a corpus over a folder, refusing one too small to mean anything."""
    paths = photographs(folder)
    if limit is not None:
        paths = paths[:limit]
    corpus = Corpus(root=folder, paths=paths, looks=tuple(LOOKS))
    check_size(corpus)
    return corpus


def check_size(corpus: Corpus) -> None:
    """Refuse a corpus below either bound, naming which one it failed."""
    if len(corpus.paths) < MIN_PICTURES:
        raise CorpusTooSmallError(
            f"{len(corpus.paths)} photographs, and {MIN_PICTURES} are needed: a corpus this "
            "small measures the photographs rather than the models"
        )
    if len(corpus.looks) < MIN_LOOKS:
        raise CorpusTooSmallError(
            f"{len(corpus.looks)} looks, and {MIN_LOOKS} are needed: with fewer, one filter "
            "decides what style means"
        )


def is_constant(image: Picture) -> bool:
    """One colour everywhere — a picture that kept nothing of its subject.

    What is read is the **interior**, one pixel in from each edge. A 3x3 filter
    leaves the outermost ring of a picture untouched, so a photograph a look
    flattened still carries its original frame: read the whole picture and the
    rule misses exactly the case it exists for, which is a look that destroyed
    the subject and left a border behind.
    """
    picture = image.convert("RGB")
    width, height = picture.size
    if width > 2 and height > 2:
        picture = picture.crop((1, 1, width - 1, height - 1))
    return all(low == high for low, high in picture.getextrema())


def looked_at(picture: Picture, look: str) -> Picture | None:
    """Apply one look, or return `None` when the result keeps no subject."""
    result = LOOKS[look](picture)
    return None if is_constant(result) else result


def images(corpus: Corpus) -> Iterator[tuple[Label, Picture]]:
    """Every image of the corpus, in a fixed order, constants left out.

    Generated rather than stored: the caller embeds a batch and lets it go.
    """
    for index, path in enumerate(corpus.paths):
        with Image.open(path) as opened:
            picture = opened.convert("RGB")
        for look in corpus.looks:
            result = looked_at(picture, look)
            if result is not None:
                yield Label(picture=index, look=look), result


def batched(
    stream: Iterator[tuple[Label, Picture]], size: int
) -> Iterator[tuple[list[Label], list[Picture]]]:
    """The stream in forward-pass-sized pieces, in the order it arrived."""
    labels: list[Label] = []
    pictures: list[Picture] = []
    for label, picture in stream:
        labels.append(label)
        pictures.append(picture)
        if len(labels) == size:
            yield labels, pictures
            labels, pictures = [], []
    if labels:
        yield labels, pictures


def present(labels: Sequence[Label]) -> tuple[int, tuple[str, ...]]:
    """What the corpus turned out to hold once the refusals are taken out."""
    pictures = {label.picture for label in labels}
    looks = sorted({label.look for label in labels}, key=tuple(LOOKS).index)
    return len(pictures), tuple(looks)


def check_present(labels: Sequence[Label]) -> None:
    """The same bounds, applied to what survived rather than to what was planned.

    `check_size` reads the plan — the folder's photographs and the look names —
    and a plan is not a corpus: a look that flattens a picture to one colour is
    dropped, and enough of those turns twenty planned photographs into two. The
    bound has to hold for the images that were actually embedded, or the command
    publishes a number from a corpus its own rules forbid.
    """
    if not labels:
        raise CorpusTooSmallError(
            "every look of every photograph was refused as one colour: there is nothing to measure"
        )
    pictures, looks = present(labels)
    if pictures < MIN_PICTURES:
        raise CorpusTooSmallError(
            f"{pictures} photographs survived the looks, and {MIN_PICTURES} are needed: "
            "a corpus this small measures the photographs rather than the models"
        )
    if len(looks) < MIN_LOOKS:
        raise CorpusTooSmallError(
            f"{len(looks)} looks survived, and {MIN_LOOKS} are needed: with fewer, one filter "
            "decides what style means"
        )
