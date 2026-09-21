"""What a client is allowed to say about a picture, and in what shape.

Tags, metadata and the original filename all arrive from outside and all end
up in the store, so they are normalised in exactly one place and the same way
wherever they enter — at upload and at a later edit alike. A tag written today
and the same tag written tomorrow must be one tag, or every filter built on
them lies.

The filename never becomes a path (`app/storage.py` builds those from an
identifier the service generated); it is still attacker-controlled text, so it
is stripped of anything that would confuse a log, a header or a reader.
"""

import json
import re
import unicodedata
from collections.abc import Iterable, Mapping
from typing import Any

#: A tag after normalisation. Lower-case, starts with a letter or digit, and
#: short enough to read in a filter.
TAG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
MAX_TAGS = 32
#: The serialised metadata bound. The multipart parser is given a larger bound
#: (see the upload router), so a value between the two is refused here, at the
#: size the requirements name, rather than by the parser.
METADATA_MAX_BYTES = 8 * 1024
METADATA_MAX_DEPTH = 4
FILENAME_MAX_LENGTH = 255


class TagError(ValueError):
    """A tag that does not survive normalisation, or too many of them."""


class MetadataError(ValueError):
    """Metadata that is not an object, or is too large or too deeply nested."""


def normalise_tag(value: str) -> str:
    """One tag: compatibility-normalised, trimmed, lower-cased, then checked."""
    tag = unicodedata.normalize("NFKC", value).strip().lower()
    if not TAG_PATTERN.match(tag):
        raise TagError(f"not a valid tag: {value!r}")
    return tag


def normalise_tags(values: Iterable[str]) -> tuple[str, ...]:
    """Every tag, normalised, in the order first seen, with duplicates gone.

    Order is kept because it is what the client wrote and it costs nothing;
    the set is what matters, and `dict.fromkeys` collapses it exactly once.
    """
    tags = tuple(dict.fromkeys(normalise_tag(value) for value in values if value.strip()))
    if len(tags) > MAX_TAGS:
        raise TagError(f"at most {MAX_TAGS} tags are allowed, got {len(tags)}")
    return tags


def split_tag_fields(values: Iterable[str]) -> tuple[str, ...]:
    """Tags as a client may write them: repeated fields, or one field holding a
    comma-separated list, or any mixture of the two."""
    written: list[str] = []
    for value in values:
        written.extend(part for part in value.split(","))
    return normalise_tags(written)


def _depth(value: Any, level: int = 1) -> int:
    if isinstance(value, dict):
        return max((_depth(item, level + 1) for item in value.values()), default=level)
    if isinstance(value, list):
        return max((_depth(item, level + 1) for item in value), default=level)
    return level


def check_metadata(value: Any) -> dict[str, Any]:
    """An already-parsed metadata value, against the shape the store accepts."""
    if not isinstance(value, dict):
        raise MetadataError("meta must be a JSON object")
    serialised = json.dumps(value, separators=(",", ":")).encode("utf-8")
    if len(serialised) > METADATA_MAX_BYTES:
        raise MetadataError(f"meta must be at most {METADATA_MAX_BYTES} bytes serialised")
    if _depth(value) > METADATA_MAX_DEPTH:
        raise MetadataError(f"meta must nest at most {METADATA_MAX_DEPTH} levels deep")
    return dict(value)


def parse_metadata(raw: str | None) -> dict[str, Any]:
    """Metadata as it arrives in a multipart field: a string holding an object.

    The length is checked before anything is parsed, so an oversized value
    never becomes objects in memory.
    """
    if raw is None or not raw.strip():
        return {}
    if len(raw.encode("utf-8")) > METADATA_MAX_BYTES:
        raise MetadataError(f"meta must be at most {METADATA_MAX_BYTES} bytes serialised")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MetadataError(f"meta is not valid JSON: {exc.msg}") from exc
    return check_metadata(parsed)


def normalise_filename(value: str | None) -> str | None:
    """The name a file arrived with, as text worth storing — or nothing.

    Reduced to its last segment under either separator, so neither a path nor a
    parent-directory segment survives to be read back as one.
    """
    if value is None:
        return None
    name = unicodedata.normalize("NFKC", value)
    name = "".join(character for character in name if unicodedata.category(character) != "Cc")
    name = name.replace("\\", "/").rsplit("/", 1)[-1].strip().strip(".")
    name = name[:FILENAME_MAX_LENGTH].strip()
    return name or None


def merge_metadata(current: Mapping[str, Any], patch: Any) -> dict[str, Any]:
    """Metadata after an edit: an explicit null clears it, anything else
    replaces it after the same checks as at upload."""
    if patch is None:
        return {}
    return check_metadata(patch)
