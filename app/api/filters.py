"""Reading a narrowing off the wire, the same way on every surface.

A filter by `meta.<key>` cannot be a declared parameter: the caller invents the
name, and the framework can only declare names it knows. So the routers read
the raw parameters — the query string, or the form fields of the picture search
— take what begins with `meta.`, and hand the rest to the one parser in
`app/services/tagging.py` (change 12, design decision 5). The OpenAPI document
describes the convention in each operation's description, for the same reason:
there is no parameter to list.

The tag filters are ordinary parameters and stay declared; they go through the
same parser so that a tag written into a filter is normalised exactly as the
tag it must match was.
"""

from collections.abc import Iterable

from app.domain import Narrowing
from app.services.tagging import MAX_META_CONDITIONS, parse_narrowing

#: What marks a query parameter or form field as a metadata condition.
META_PREFIX = "meta."

#: One type for every narrowing this service will not apply: the message says
#: which value was wrong, and a client acts on the type.
INVALID_FILTER_TYPE = "/errors/invalid-filter"

#: The convention, for the operations that accept it. In the description rather
#: than in a parameter, because `meta.<key>` has no fixed name.
NARROWING_DESCRIPTION = (
    "Narrow it to the assets that carry something: `tags_all` (every one of a comma-separated "
    "list), `tags_any` (at least one of them), and `meta.<key>=<value>` for top-level equality "
    f"in an asset's metadata — at most {MAX_META_CONDITIONS} of those, each key matching "
    "`^[a-z0-9_]{1,64}$`, and no key twice. The forms combine. A narrowing that is not "
    "acceptable is 422 `/errors/invalid-filter` naming the value, and nothing is searched."
)


def narrowing_from(
    parameters: Iterable[tuple[str, str]],
    *,
    tags_all: str | None = None,
    tags_any: str | None = None,
) -> Narrowing:
    """The filter a request carries, or `NarrowingError` naming what was wrong.

    `parameters` is the request's raw pairs — repeated names included, which is
    why it is not a mapping: the same metadata key given twice is a mistake the
    parser has to be able to see.
    """
    conditions = [
        (key[len(META_PREFIX) :], value) for key, value in parameters if key.startswith(META_PREFIX)
    ]
    return parse_narrowing(tags_all=tags_all, tags_any=tags_any, meta=conditions)
