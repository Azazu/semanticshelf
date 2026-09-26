"""The slice of the demo corpus the README's screenshots are taken from.

`make demo` fetches whatever the dataset's licence filter allows, which is a
fair sample of COCO — and a fair sample of COCO includes bathrooms. The pictures
on a project's front page are the one place where "whatever came back" is not
good enough, so this copies a subset into a folder of its own: animals, people
doing something, vehicles, road signs, food and plants — and nothing whose only
subject is a fixture.

It copies rather than links because the folder import refuses a link that leaves
its tree (change 7), and it copies the sidecar with each picture so the tags and
the provenance travel too.

    uv run python scripts/screenshot_corpus.py            # into .data/demo-shopfront
    uv run semanticshelf index-folder .data/demo-shopfront --tags shopfront

Nothing here decides what the *service* can hold; it decides what the pictures
in `docs/images/` show.
"""

import json
import shutil
import sys
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / ".data" / "demo" / "pictures"
TARGET = ROOT / ".data" / "demo-shopfront"

#: A picture is taken when it has one of these as a subject…
SUBJECTS = frozenset(
    {
        "dog",
        "cat",
        "horse",
        "sheep",
        "cow",
        "elephant",
        "bear",
        "zebra",
        "giraffe",
        "bird",
        "bicycle",
        "motorcycle",
        "boat",
        "airplane",
        "train",
        "bus",
        "truck",
        "car",
        "traffic-light",
        "stop-sign",
        "fire-hydrant",
        "parking-meter",
        "surfboard",
        "skis",
        "snowboard",
        "kite",
        "frisbee",
        "sports-ball",
        "skateboard",
        "tennis-racket",
        "baseball-bat",
        "baseball-glove",
        "potted-plant",
        "umbrella",
        "bench",
        "clock",
    }
)
#: …and everything else in it is one of these, or a subject. Anything else — a
#: bathroom fixture, a hair drier, somebody's dining table — keeps it out.
COMPANIONS = frozenset(
    {
        "person",
        "backpack",
        "handbag",
        "suitcase",
        "tie",
        "hat",
        "sunglasses",
        "bottle",
        "cup",
        "banana",
        "apple",
        "orange",
        "broccoli",
        "carrot",
        "book",
        "vase",
        "chair",
        "dining-table",
    }
)
#: How many to take. Enough for a grid that looks like a corpus, few enough to
#: index in a couple of minutes.
WANTED = 80


def pictures() -> Iterator[tuple[Path, Path, list[str]]]:
    for sidecar in sorted(SOURCE.rglob("*.json")):
        picture = sidecar.with_suffix(".jpg")
        if not picture.exists():
            continue
        tags = json.loads(sidecar.read_text(encoding="utf-8")).get("tags", [])
        yield picture, sidecar, tags


def wanted(tags: list[str]) -> bool:
    if not tags:
        return False
    if not SUBJECTS.intersection(tags):
        return False
    return all(tag in SUBJECTS or tag in COMPANIONS for tag in tags)


def main() -> int:
    if not SOURCE.is_dir():
        print(f"no corpus at {SOURCE} — run `make demo` first", file=sys.stderr)
        return 2

    TARGET.mkdir(parents=True, exist_ok=True)
    taken = 0
    for picture, sidecar, tags in pictures():
        if taken >= WANTED or not wanted(tags):
            continue
        shutil.copy2(picture, TARGET / picture.name)
        shutil.copy2(sidecar, TARGET / sidecar.name)
        taken += 1

    print(f"{taken} pictures copied into {TARGET.relative_to(ROOT)}")
    if taken < WANTED:
        print(f"(wanted {WANTED}; fetch more with `demo-dataset download --count …`)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
