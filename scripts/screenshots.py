"""Capture the screenshots the README uses, from a real service and a real page.

`make screenshots` starts the API and the demo interface on ports it picks,
drives a headless browser through three pages and writes them to `docs/images/`.

Two rules this script keeps, because the alternative is a repository that grows
stale pictures and a machine that grows orphaned servers:

- what is captured is the real thing — no fixtures, no mock, no hand-cropping;
- whatever happens, both children are stopped before this exits, and that is
  checked rather than assumed.
"""

import os
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
IMAGES = ROOT / "docs" / "images"
VIEWPORT = {"width": 1440, "height": 900}
START_TIMEOUT_SECONDS = 90
QUERY = "a red stop sign at a junction"


def free_port() -> int:
    """A port nothing is listening on, at the moment it was asked for."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@contextmanager
def started(command: list[str], *, url: str, name: str, env: dict[str, str]) -> Iterator[None]:
    """Run a server for as long as the block lasts, and not one moment longer.

    The child gets its own process group so the whole tree can be signalled:
    uvicorn and streamlit both spawn children of their own, and killing only the
    launcher leaves a listening port behind.
    """
    process = subprocess.Popen(  # noqa: S603 - the command is built here, not taken from input
        command,
        cwd=ROOT,
        env={**os.environ, **env},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        _await(url, name=name, process=process)
        yield
    finally:
        _stop(process, name=name)


def _await(url: str, *, name: str, process: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"{name} stopped before it answered (exit {process.returncode})")
        try:
            httpx.get(url, timeout=2.0)
        except httpx.HTTPError:
            time.sleep(0.5)
        else:
            return
    raise RuntimeError(f"{name} did not answer at {url} within {START_TIMEOUT_SECONDS}s")


def _stop(process: subprocess.Popen[bytes], *, name: str) -> None:
    """Signal the whole group, then make sure it is gone."""
    if process.poll() is not None:
        return
    for attempt in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(os.getpgid(process.pid), attempt)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=10)
            return
        except subprocess.TimeoutExpired:
            continue
    raise RuntimeError(f"{name} would not stop")


def corpus_is_there(api: str) -> bool:
    stats = httpx.get(f"{api}/api/v1/stats", timeout=10.0).json()
    return bool(stats["assets"])


def capture(ui: str) -> None:
    """Three pages, in the order a person meets them."""
    from playwright.sync_api import sync_playwright

    IMAGES.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport=VIEWPORT)
            page.goto(ui, wait_until="networkidle")

            page.get_by_label("What are you looking for?").fill(QUERY)
            page.get_by_role("button", name="Search").click()
            page.wait_for_selector("img", timeout=60_000)
            page.wait_for_timeout(1_500)  # the thumbnails the browser is still fetching
            page.screenshot(path=IMAGES / "search.png")

            page.get_by_role("link", name="Browse").click()
            page.wait_for_selector("img", timeout=60_000)
            page.wait_for_timeout(1_500)
            page.screenshot(path=IMAGES / "browse.png")

            page.get_by_role("link", name="Status").click()
            page.wait_for_timeout(1_500)
            page.screenshot(path=IMAGES / "status.png")
        finally:
            browser.close()


def main() -> int:
    api_port, ui_port = free_port(), free_port()
    api = f"http://127.0.0.1:{api_port}"
    ui = f"http://127.0.0.1:{ui_port}"

    with started(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "--factory",
            "app.main:create_app",
            "--host",
            "127.0.0.1",
            "--port",
            str(api_port),
        ],
        url=f"{api}/health",
        name="the API",
        env={},
    ):
        if not corpus_is_there(api):
            print("the store is empty — run `make demo` first, and there will be something to see")
            return 2
        with started(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                "ui/app.py",
                "--server.port",
                str(ui_port),
                "--server.headless",
                "true",
                "--browser.gatherUsageStats",
                "false",
            ],
            url=ui,
            name="the interface",
            env={"API_BASE_URL": api},
        ):
            capture(ui)

    for name in ("search.png", "browse.png", "status.png"):
        print(f"wrote docs/images/{name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
