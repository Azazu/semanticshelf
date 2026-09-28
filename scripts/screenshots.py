"""Capture the screenshots the README uses, from a real service and a real page.

`make screenshots` starts the API and the demo interface on ports it picks,
drives a headless browser through all five pages and writes them to
`docs/images/`.

Two rules this script keeps, because the alternative is a repository that grows
stale pictures and a machine that grows orphaned servers:

- what is captured is the real thing — no fixtures, no mock, no hand-cropping;
- whatever happens, both children are stopped before this exits, and that is
  checked rather than assumed.

What is *in* the store is chosen, though, and deliberately:
`scripts/screenshot_corpus.py` copies the part of the demo corpus a front page
should show. The pictures are still the dataset's own.
"""

import os
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
IMAGES = ROOT / "docs" / "images"
VIEWPORT = {"width": 1440, "height": 900}
START_TIMEOUT_SECONDS = 90
QUERY = "people playing tennis on a sunny court"


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
    group = os.getpgid(process.pid)
    try:
        _await(url, name=name, process=process)
        yield
    finally:
        _stop(process, group=group, name=name)


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


def _group_is_gone(group: int) -> bool:
    """Whether any process is still in that group.

    Signal 0 checks for existence without sending anything, and it answers for
    the *group* — which is the question, because uvicorn and streamlit both
    spawn children and a leader that has exited says nothing about them.
    """
    try:
        os.killpg(group, 0)
    except ProcessLookupError:
        return True
    except PermissionError:  # pragma: no cover - something else owns it now
        return False
    return False


def _stop(process: subprocess.Popen[bytes], *, group: int, name: str) -> None:
    """Signal the whole group, then make sure the whole group is gone.

    The leader exiting is not the end of it: Gate 2 caught this returning as
    soon as `process.poll()` answered, which leaves a surviving child holding
    the port it was listening on.
    """
    for attempt in (signal.SIGTERM, signal.SIGKILL):
        if _group_is_gone(group):
            break
        with suppress(ProcessLookupError):
            os.killpg(group, attempt)
        with suppress(subprocess.TimeoutExpired):
            process.wait(timeout=10)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not _group_is_gone(group):
            time.sleep(0.2)
    if not _group_is_gone(group):
        raise RuntimeError(f"{name} left something running in process group {group}")


def corpus_is_there(api: str) -> bool:
    stats = httpx.get(f"{api}/api/v1/stats", timeout=10.0).json()
    return bool(stats["assets"])


def a_picture_to_upload() -> Path:
    """Something for the Upload page's form to be holding.

    The demo corpus if it is there — a real picture with a real name is what the
    page will show a person — and otherwise one drawn here, so the capture works
    on a machine that has not fetched the dataset.
    """
    pictures = sorted((ROOT / ".data" / "demo" / "pictures").rglob("*.jpg"))
    if pictures:
        return pictures[0]
    from PIL import Image

    drawn = ROOT / ".data" / "screenshot-upload.png"
    drawn.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (640, 480), (52, 96, 148)).save(drawn)
    return drawn


def capture(ui: str) -> None:
    """Five pages, in the order a person meets them."""
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

            # "Find similar" is an action under a thumbnail, so the page it
            # leads to is captured the way a person actually reaches it.
            page.get_by_role("button", name="Find similar").first.click()
            page.wait_for_selector("img", timeout=60_000)
            page.wait_for_timeout(1_500)
            page.screenshot(path=IMAGES / "similar.png")

            # The Upload page is a form: empty, it shows nothing about what it
            # accepts, so it is filled before it is photographed. Nothing is
            # submitted — a screenshot run must not add to the corpus it is
            # photographing.
            page.get_by_role("link", name="Upload").click()
            page.wait_for_timeout(1_000)
            page.set_input_files("input[type=file]", str(a_picture_to_upload()))
            page.get_by_label("Tags").fill("demo, outdoors")
            # Enter, so the field is a value rather than an edit in progress;
            # then the heading, so nothing is focused. Streamlit draws both an
            # unapplied input and a focused one in the theme's primary colour,
            # which is red here — in a still picture that reads as an error.
            page.get_by_label("Tags").press("Enter")
            page.get_by_role("heading", name="Upload").click()
            # And the pointer off the heading again: Streamlit hangs an anchor
            # link beside whatever the mouse is over, and the picture would keep it.
            page.mouse.move(VIEWPORT["width"] - 10, VIEWPORT["height"] - 10)
            page.wait_for_timeout(1_500)
            page.screenshot(path=IMAGES / "upload.png")

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

    for name in ("search.png", "similar.png", "browse.png", "upload.png", "status.png"):
        print(f"wrote docs/images/{name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
