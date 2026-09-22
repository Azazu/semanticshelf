"""Does the ranking mean anything?

Every other test of the search runs against a stand-in whose vectors are
arithmetic, which proves the plumbing and nothing about the model. This one
asks the real checkpoint a question in words and checks that the picture the
words describe comes first — the only test that can catch the two towers being
wired to each other wrongly.

Marked `models`: it needs the real weights, so neither `make check` nor CI runs
it. `make test-models`.
"""

from collections.abc import Iterator

import numpy as np
import pytest
from PIL import Image as PILImage
from PIL import ImageDraw
from PIL.Image import Image

from app.core.settings import Settings
from app.ml.clip import ClipEmbedder

pytestmark = pytest.mark.models

UNREACHABLE_DATABASE_URL = "postgresql+asyncpg://127.0.0.1:1/nowhere"


@pytest.fixture(scope="module")
def embedder() -> Iterator[ClipEmbedder]:
    settings = Settings(_env_file=None, database_url=UNREACHABLE_DATABASE_URL)
    yield ClipEmbedder.load(settings)


def solid(colour: tuple[int, int, int]) -> Image:
    return PILImage.new("RGB", (224, 224), color=colour)


def circle_on(background: tuple[int, int, int], colour: tuple[int, int, int]) -> Image:
    picture = PILImage.new("RGB", (224, 224), color=background)
    ImageDraw.Draw(picture).ellipse((40, 40, 184, 184), fill=colour)
    return picture


#: Four pictures a sentence can tell apart, and the words for each.
GALLERY: dict[str, Image] = {
    "red": solid((220, 30, 30)),
    "green": solid((30, 170, 60)),
    "blue circle": circle_on((250, 250, 250), (30, 60, 220)),
    "black and white": circle_on((255, 255, 255), (0, 0, 0)),
}


def ranking(embedder: ClipEmbedder, query: str) -> list[str]:
    """The gallery, ordered as a search would order it for this query."""
    images = embedder.embed_images(list(GALLERY.values())).vectors
    text = embedder.embed_text([query]).vectors[0]
    scores = np.asarray(images) @ np.asarray(text)
    return [name for _, name in sorted(zip(-scores, GALLERY, strict=True))]


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("a solid red background", "red"),
        ("a solid green background", "green"),
        ("a blue circle on a white background", "blue circle"),
        ("a black circle on a white background", "black and white"),
    ],
)
def test_the_words_find_the_picture_they_describe(
    embedder: ClipEmbedder, query: str, expected: str
) -> None:
    order = ranking(embedder, query)

    assert order[0] == expected, f"{query!r} ranked {order}"


def test_a_query_that_describes_nothing_still_answers(embedder: ClipEmbedder) -> None:
    """A search has no notion of "no match": a threshold is how a caller says
    that, which is why `min_score` exists and why this returns an order."""
    order = ranking(embedder, "a plate of spaghetti")

    assert sorted(order) == sorted(GALLERY)
