"""What a narrowing means in SQL, in one place.

A search narrows the rows its vector query ranks; the listing narrows the rows
it pages through. Same filter object, same predicates, one definition — so that
a person who narrows a listing and a person who narrows a search are asking the
same question of the same column.

Its own module rather than either repository's: `assets` imports `jobs`, which
imports `embeddings`, so the one thing both ends need cannot live at either end.
"""

import sqlalchemy as sa

from app.domain import Narrowing
from app.models import Asset as AssetRow


def narrowing_clauses(narrowing: Narrowing) -> list[sa.ColumnElement[bool]]:
    """The narrowing as predicates on the `assets` row.

    Containment in every case, so every one of them is answered by a GIN index:
    `@>` for all of a set of tags, `&&` for any of them, and `@>` again for
    top-level metadata equality. The values are bound, never rendered.
    """
    clauses: list[sa.ColumnElement[bool]] = []
    if narrowing.tags_all:
        clauses.append(AssetRow.tags.contains(list(narrowing.tags_all)))
    if narrowing.tags_any:
        clauses.append(AssetRow.tags.overlap(list(narrowing.tags_any)))
    if narrowing.meta:
        clauses.append(AssetRow.meta.contains(dict(narrowing.meta)))
    return clauses
