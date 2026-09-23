"""The surface of `semanticshelf index missing`: its options and its help.

What it does to a store is in `tests/integration/test_backfill.py`; what it
offers an operator is here, where no database is needed. Colour is turned off
and the escapes are stripped, because CI sets `FORCE_COLOR` and a styled option
name is split across fragments that a substring search then misses.
"""

import re

from typer.testing import CliRunner

from app.cli import app
from app.domain import DINOV2_LARGE

ANSI = re.compile(r"\x1b\[[0-9;]*m")
#: The box a help panel is drawn in. Removed before the text is flattened, or
#: the border would land in the middle of a sentence that wrapped.
BOX = re.compile(r"[│─╭╮╰╯├┤]")


def run(*arguments: str) -> tuple[int, str]:
    """The command's help as one line of text.

    Flattened on purpose: the terminal wraps a sentence wherever it runs out of
    width, so any phrase worth asserting is eventually split across two lines by
    a change in wording somewhere else entirely.
    """
    result = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb"}).invoke(app, list(arguments))
    plain = BOX.sub(" ", ANSI.sub("", result.output))
    return result.exit_code, " ".join(plain.split())


def test_the_command_is_listed_in_the_top_level_help() -> None:
    code, output = run("--help")

    assert code == 0
    assert "index" in output


def test_the_group_lists_what_it_can_backfill() -> None:
    code, output = run("index", "--help")

    assert code == 0
    assert "missing" in output


def test_the_options_are_documented() -> None:
    code, output = run("index", "missing", "--help")

    assert code == 0
    assert "--model" in output
    assert "--no-index" in output
    assert "every enabled model" in output, "what the default is, not only that there is one"


def test_the_help_says_what_it_will_not_do() -> None:
    """The rule an operator most needs before running it: work that already
    failed is not retried by this command."""
    _, output = run("index", "missing", "--help")

    assert "failed" in output
    assert "reindex" in output


def test_the_help_does_not_need_a_database() -> None:
    """`--help` must answer on a machine with nothing configured: the command
    builds its settings inside itself, not at import."""
    code, output = run("index", "missing", "--help")

    assert code == 0
    assert DINOV2_LARGE not in output, "no model key is hard-coded into the help"
