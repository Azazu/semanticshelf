"""The screenshot script stops what it started — the whole tree of it.

A server run for a screenshot is started in its own process group, and uvicorn
and streamlit both spawn children. Watching only the launcher is how a port
stays held after the script says it is done, so what is checked here is the
group.
"""

import importlib.util
import os
import subprocess
import time
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "screenshots.py"


def screenshots() -> ModuleType:
    """The script, imported as a module — it is not a package."""
    spec = importlib.util.spec_from_file_location("screenshots", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def module() -> ModuleType:
    return screenshots()


def a_leader_that_leaves_a_child() -> subprocess.Popen[bytes]:
    """A process that spawns a long-lived child and exits immediately.

    This is what a server looks like a moment after it is signalled badly: the
    launcher is gone and the thing holding the port is not.
    """
    return subprocess.Popen(
        ["sh", "-c", "sleep 120 & exit 0"],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def test_a_child_that_outlives_its_leader_is_stopped_too(module: ModuleType) -> None:
    process = a_leader_that_leaves_a_child()
    group = os.getpgid(process.pid)
    process.wait(timeout=10)  # the leader is gone; its child is not
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and module._group_is_gone(group):
        time.sleep(0.1)
    assert not module._group_is_gone(group), "the child is what this test is about"

    module._stop(process, group=group, name="the probe")

    assert module._group_is_gone(group), "nothing of that run is left running"


def test_stopping_something_already_gone_is_not_an_error(module: ModuleType) -> None:
    process = subprocess.Popen(["true"], start_new_session=True)
    group = os.getpgid(process.pid)
    process.wait(timeout=10)

    module._stop(process, group=group, name="the probe")

    assert module._group_is_gone(group)
