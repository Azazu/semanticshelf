"""The surface of `semanticshelf worker`: its options, and what it refuses.

What it does to a queue is in `tests/integration/test_worker_process.py`, where
it runs as a process and is sent real signals. What it offers an operator is
here, where nothing is started at all.
"""

import re

import pytest
from typer.testing import CliRunner

from app.cli import app

ANSI = re.compile(r"\x1b\[[0-9;]*m")
BOX = re.compile(r"[│─╭╮╰╯├┤]")


def run(*arguments: str) -> tuple[int, str]:
    result = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb"}).invoke(app, list(arguments))
    plain = BOX.sub(" ", ANSI.sub("", result.output))
    return result.exit_code, " ".join(plain.split())


def test_the_command_is_listed_in_the_top_level_help() -> None:
    code, output = run("--help")

    assert code == 0
    assert "worker" in output


def test_its_help_says_what_stops_it_and_what_the_switch_does() -> None:
    code, output = run("worker", "--help")

    assert code == 0
    assert "--once" in output and "--batch" in output
    assert "SIGTERM" in output, "how an operator stops it belongs in its own help"
    assert "INDEXING_RUNNER" in output


@pytest.mark.parametrize("batch", ["0", "-1"], ids=["zero", "negative"])
def test_a_batch_that_is_not_a_batch_is_refused(batch: str) -> None:
    """Refused by the option, before a connection is opened — the test would
    otherwise reach the unreachable database of this suite and say so."""
    code, output = run("worker", "--batch", batch)

    assert code == 2, output
    assert "--batch" in output
