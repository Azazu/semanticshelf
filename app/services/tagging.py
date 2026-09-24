"""What a client is allowed to say about a picture, and in what shape.

Tags, metadata and the original filename all arrive from outside and all end
up in the store, so they are normalised in exactly one place and the same way
wherever they enter — at upload and at a later edit alike. A tag written today
and the same tag written tomorrow must be one tag, or every filter built on
them lies.

The same module reads a *narrowing* — what a search or a listing is willing to
consider — for the same reason: a tag in a narrowing has to be normalised the
way the tag it must match was normalised, and one place doing both is the only
way that stays true.

The filename never becomes a path (`app/storage.py` builds those from an
identifier the service generated); it is still attacker-controlled text, so it
is stripped of anything that would confuse a log, a header or a reader.
"""

import json
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from app.domain import Narrowing

#: A tag after normalisation. Lower-case, starts with a letter or digit, and
#: short enough to read in a filter.
#:
#: `\Z` rather than `$` in this and every other pattern that decides whether a
#: value is acceptable: Python's `$` also matches *before* a final newline, so
#: `^...$` accepts `dragon\n` — a value the shape does not describe. Anything
#: that validates has to match the whole string, terminal newline included
#: (change 12, Gate 2 finding 1).
TAG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}\Z")
MAX_TAGS = 32
#: The serialised metadata bound. The multipart parser is given a larger bound
#: (see the upload router), so a value between the two is refused here, at the
#: size the requirements name, rather than by the parser.
METADATA_MAX_BYTES = 8 * 1024
METADATA_MAX_DEPTH = 4
FILENAME_MAX_LENGTH = 255

#: A metadata key a narrowing may name (FR-FLT-3). Narrower than what metadata
#: may contain: a filter names a key a person typed into a URL.
NARROWING_KEY_PATTERN = re.compile(r"^[a-z0-9_]{1,64}\Z")
#: How many metadata conditions one narrowing may carry (FR-FLT-3).
MAX_META_CONDITIONS = 5


class TagError(ValueError):
    """A tag that does not survive normalisation, or too many of them."""


class MetadataError(ValueError):
    """Metadata that is not an object, or is too large or too deeply nested."""


class NarrowingError(ValueError):
    """A narrowing this service will not apply, and why.

    One class for every way of getting one wrong — a tag that is not a tag, a
    metadata key outside its shape, too many conditions, the same key twice —
    so that every surface answers the same problem details and the message is
    what differs.
    """


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


def parse_narrowing(
    *,
    tags_all: str | None = None,
    tags_any: str | None = None,
    meta: Sequence[tuple[str, str]] = (),
) -> Narrowing:
    """Read a narrowing from what a client wrote, or refuse it.

    `tags_all` and `tags_any` arrive as a client writes them — comma-separated,
    possibly repeated — and are normalised exactly as the tags they must match
    were normalised at upload. `meta` arrives as the pairs a router pulled out
    of the query string or the form, with the `meta.` prefix already removed,
    because a parameter whose name the caller invents cannot be declared.

    Refused, each naming what was wrong: a tag that does not survive
    normalisation, a key outside `^[a-z0-9_]{1,64}$`, more than five conditions,
    and the same key twice — the last because two values for one key can never
    both hold, so a request that carries them is a mistake worth reporting
    rather than an empty page worth guessing at.
    """
    try:
        required = split_tag_fields([tags_all]) if tags_all else ()
        alternatives = split_tag_fields([tags_any]) if tags_any else ()
    except TagError as error:
        raise NarrowingError(str(error)) from error

    if len(meta) > MAX_META_CONDITIONS:
        raise NarrowingError(
            f"at most {MAX_META_CONDITIONS} metadata conditions are allowed, got {len(meta)}"
        )
    conditions: dict[str, str] = {}
    for key, value in meta:
        if not NARROWING_KEY_PATTERN.match(key):
            raise NarrowingError(f"not a valid metadata key: {key!r}")
        if key in conditions:
            raise NarrowingError(f"metadata key given twice: {key!r}")
        conditions[key] = value
    return Narrowing(tags_all=required, tags_any=alternatives, meta=conditions)


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
