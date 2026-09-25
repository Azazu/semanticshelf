"""The names a benchmark may create, and the ones it refuses.

`scripts/bench_schema.py` is the guard between a published measurement command
and somebody's corpus: its schema name is interpolated into `CREATE SCHEMA`,
into table DDL and into `DROP SCHEMA ... CASCADE`, so the check that decides
which names are allowed is the thing that decides whether a command can delete
data it did not create. It is checked here on its own, before any database is
involved — a refusal that happens at the edge is a refusal that never reached a
connection.
"""

import pytest

from tests.scripts import script_module

guard = script_module("bench_schema")


ACCEPTED = ("filter_benchmark", "index_benchmark", "_private", "bench_2026", "a" * 49)

REFUSED = (
    # where the service's own tables live, and what the database reserves
    "public",
    "pg_catalog",
    "pg_temp_1",
    "information_schema",
    # `\Z`, not `$`: Python's `$` matches before a final newline, so `^...$`
    # accepts this — and SQL reads it as `public` followed by whitespace, which
    # the equality check against the protected names would not catch (change 12,
    # Gate 2 finding 1).
    "public\n",
    "public\n ",
    # anything that would have to be quoted, or that closes the statement
    "Filter_Benchmark",
    'x"; DROP SCHEMA public CASCADE; --',
    "x; DROP",
    "with space",
    "dash-name",
    "1leading_digit",
    "",
    "a" * 50,
)


@pytest.mark.parametrize("name", ACCEPTED)
def test_a_plain_lowercase_name_is_usable(name: str) -> None:
    assert guard.unusable(name) is None


@pytest.mark.parametrize("name", REFUSED)
def test_a_name_that_could_reach_the_store_is_refused(name: str) -> None:
    why = guard.unusable(name)
    assert why is not None, f"{name!r} was accepted"
    assert repr(name) in why or name in why, "the refusal names the offender"


def test_the_pattern_ends_the_string_rather_than_the_line() -> None:
    """The one that cost a Gate 2 round: `$` would accept a trailing newline."""
    assert guard.SCHEMA_PATTERN.match("public\n") is None
    assert guard.SCHEMA_PATTERN.match("public") is not None


def test_the_protected_names_are_the_ones_that_matter() -> None:
    assert "public" in guard.PROTECTED_SCHEMAS
    assert {"pg_catalog", "information_schema"} <= guard.PROTECTED_SCHEMAS
