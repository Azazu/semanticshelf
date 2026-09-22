"""The demo corpus: one dataset, its licences, and a bounded download.

Nothing the service imports may reach this module — it is the only place in the
repository that fetches from the internet, and NFR-SEC-4 promises the API and
the worker never do (`tests/unit/test_layering_demo.py` keeps that true). The
only way in is the `demo-dataset` command.

Everything the dataset says is data. Its manifest names files, addresses and
licences; none of those becomes a path, an address or a permission here. The
command builds every address from its own base and an identifier it validated,
decides every licence against the manifest's own table, and writes every file
under a name it derived itself.
"""

import json
import zipfile
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.tagging import MAX_TAGS, TagError, normalise_tag

#: What the corpus is, as it is recorded on every asset it produces.
DATASET = "coco-val2017"

#: The bucket, by its path-style S3 address rather than by the name COCO
#: documents: `images.cocodataset.org` serves no certificate for its own name
#: (`SSL: no alternative certificate subject name matches target hostname`), and
#: the addresses inside the manifest are plain `http://`. The same objects are
#: here, over TLS that verifies. Design decision 3.
BASE_URL = "https://s3.amazonaws.com/images.cocodataset.org"
ARCHIVE_PATH = "annotations/annotations_trainval2017.zip"
PICTURES_PATH = "val2017"

#: The one member of the archive this command reads, by exact name.
MANIFEST_MEMBER = "annotations/instances_val2017.json"

#: Three bounds, because there are three kinds of object. A picture is what the
#: service accepts as a picture (`MAX_UPLOAD_BYTES`); the archive is 241 MiB
#: today, so its bound is its own; the member inside it is ~46 MiB today.
ARCHIVE_MAX_BYTES = 512 * 1024 * 1024
MEMBER_MAX_BYTES = 128 * 1024 * 1024

#: The licences whose pictures may be taken, by URL rather than by the id the
#: manifest indexes them with: an id is that file's own numbering, a URL states
#: the licence. NoDerivs is absent on purpose — the service re-encodes a
#: thumbnail of everything it stores, and a thumbnail is a derivative work.
ACCEPTED_LICENCES = frozenset(
    {
        "http://creativecommons.org/licenses/by/2.0/",
        "http://creativecommons.org/licenses/by-sa/2.0/",
        "http://flickr.com/commons/usage/",
        "http://www.usa.gov/copyright.shtml",
    }
)

#: How many pictures a download takes when it is not told otherwise.
DEFAULT_COUNT = 500


class ManifestError(Exception):
    """The archive or the manifest inside it is not what was expected."""


@dataclass(frozen=True, slots=True)
class Picture:
    """One picture of the corpus, as the manifest describes it.

    `identifier` is the dataset's own, validated to be a positive integer,
    because it is what every name this command writes is built from.
    """

    identifier: int
    licence: str
    tags: tuple[str, ...]

    @property
    def source_url(self) -> str:
        """Where the picture can be seen. Built here, never read from the
        manifest: attribution has to point at something this command trusts."""
        return f"{BASE_URL}/{PICTURES_PATH}/{self.identifier:012d}.jpg"

    def provenance(self) -> dict[str, str]:
        """The keys FR-TAG-2 reserves, as far as this dataset supplies them.

        COCO's image entries carry no author, so the key is absent rather than
        invented, and attribution is by address.
        """
        return {
            "dataset": DATASET,
            "dataset_id": str(self.identifier),
            "licence": self.licence,
            "source_url": self.source_url,
        }


def tag_of(label: str) -> str | None:
    """A dataset's label as a tag, or `None` when it cannot be one.

    A label is not a tag: `normalise_tag` lower-cases and trims and then refuses
    a space, so `traffic light` would be lost. This conversion — runs of
    whitespace become the separator a tag may carry — belongs to the demo
    corpus, and the service's own rule is left exactly as the API enforces it.
    """
    joined = "-".join(label.split())
    if not joined:
        return None
    try:
        return normalise_tag(joined)
    except TagError:
        return None


def tags_of(labels: Iterable[str]) -> tuple[str, ...]:
    """Every label that can be a tag, in order, deduplicated and bounded."""
    tags = dict.fromkeys(tag for tag in (tag_of(label) for label in labels) if tag is not None)
    return tuple(tags)[:MAX_TAGS]


def read_manifest(archive: Path) -> dict[str, Any]:
    """The one member of the archive, by exact name and under its bound.

    Nothing is extracted to disk: the member is read into memory, so an entry
    named `../…` has nothing to escape into. A member under another name is not
    looked for, which is the same refusal as a member that is absent.
    """
    try:
        with zipfile.ZipFile(archive) as bundle:
            try:
                entry = bundle.getinfo(MANIFEST_MEMBER)
            except KeyError as error:
                raise ManifestError(f"the archive does not contain {MANIFEST_MEMBER!r}") from error
            if entry.file_size > MEMBER_MAX_BYTES:
                raise ManifestError(
                    f"{MANIFEST_MEMBER!r} declares {entry.file_size} bytes, "
                    f"above the {MEMBER_MAX_BYTES} allowed"
                )
            raw = bundle.read(entry)
    except zipfile.BadZipFile as error:
        raise ManifestError(f"not a readable archive: {archive.name}") from error
    try:
        manifest = json.loads(raw)
    except ValueError as error:
        raise ManifestError(f"{MANIFEST_MEMBER!r} is not JSON") from error
    if not isinstance(manifest, dict):
        raise ManifestError(f"{MANIFEST_MEMBER!r} is not an object")
    return manifest


def _licence_urls(manifest: Mapping[str, Any]) -> dict[int, str]:
    """The manifest's own licence table, by the id it indexes pictures with."""
    urls: dict[int, str] = {}
    for licence in manifest.get("licenses") or ():
        if isinstance(licence, dict) and isinstance(licence.get("id"), int):
            url = licence.get("url")
            if isinstance(url, str):
                urls[licence["id"]] = url
    return urls


def _labels_by_picture(manifest: Mapping[str, Any]) -> dict[int, list[str]]:
    """Which object categories each picture is annotated with."""
    categories = {
        category["id"]: category["name"]
        for category in manifest.get("categories") or ()
        if isinstance(category, dict)
        and isinstance(category.get("id"), int)
        and isinstance(category.get("name"), str)
    }
    labels: dict[int, list[str]] = {}
    for annotation in manifest.get("annotations") or ():
        if not isinstance(annotation, dict):
            continue
        name = categories.get(annotation.get("category_id"))
        image_id = annotation.get("image_id")
        if name is None or not isinstance(image_id, int):
            continue
        for_picture = labels.setdefault(image_id, [])
        if name not in for_picture:
            for_picture.append(name)
    return labels


@dataclass(frozen=True, slots=True)
class Selection:
    """What the manifest offers, once the licences have decided."""

    pictures: tuple[Picture, ...]
    refused_for_licence: int


def select(manifest: Mapping[str, Any]) -> Selection:
    """The pictures whose licence permits reuse, in the manifest's own order.

    A picture with no licence, with an id the manifest's table does not define,
    or with a licence outside the accepted list is refused and counted. The
    order is the manifest's, so the same count fetches the same corpus.
    """
    urls = _licence_urls(manifest)
    labels = _labels_by_picture(manifest)
    pictures: list[Picture] = []
    refused = 0
    for image in manifest.get("images") or ():
        if not isinstance(image, dict):
            continue
        identifier = image.get("id")
        if not isinstance(identifier, int) or isinstance(identifier, bool) or identifier <= 0:
            refused += 1
            continue
        declared = image.get("license")
        licence = urls.get(declared) if isinstance(declared, int) else None
        if licence is None or licence not in ACCEPTED_LICENCES:
            refused += 1
            continue
        pictures.append(
            Picture(
                identifier=identifier,
                licence=licence,
                tags=tags_of(labels.get(identifier, ())),
            )
        )
    return Selection(pictures=tuple(pictures), refused_for_licence=refused)


def wanted(selection: Selection, *, count: int) -> Iterator[Picture]:
    """The first `count` pictures of a selection. A count of zero yields none."""
    if count < 0:
        raise ValueError("count must not be negative")
    return iter(selection.pictures[:count])


def sidecar_of(picture: Picture) -> dict[str, Any]:
    """What is written beside a picture: its tags and where it came from."""
    return {"tags": list(picture.tags), "meta": picture.provenance()}


def licence_notice(accepted: Sequence[str] = tuple(sorted(ACCEPTED_LICENCES))) -> str:
    """What every run prints, whether or not it downloaded anything."""
    lines = [
        f"{DATASET}: the annotations are CC BY 4.0 (COCO Consortium); the pictures belong to",
        "their photographers and are taken only under these licences:",
        *(f"  {url}" for url in accepted),
        "Attribution is by address: the manifest records no author name.",
        "Details: docs/reference/demo-dataset.md",
    ]
    return "\n".join(lines)
