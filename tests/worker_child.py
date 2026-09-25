"""The worker, in a child process, held where a test needs it.

Change 13 claims things only a process can prove: that a real signal reaches a
runner, that it finishes the batch it holds, that a second signal ends it, and
that two of them share one queue. Proving those needs the real command — and the
real command would load real weights, which no suite here ever does.

So this is the command's own runtime with two things added and nothing removed:

- **the fake embedder every suite uses**, which makes weights unnecessary;
- **a barrier inside the work**, which makes the test deterministic. The moment
  the fake is asked to embed, it announces that this process is holding claimed
  work (`held-<pid>`) and waits for the parent to say `release`. Between those
  two moments the child cannot finish the batch, cannot claim another, and
  cannot exit — so a signal sent then lands exactly where the test means it to.

A third file closes the loop in the other direction: the stop handler writes
`signalled-<pid>` before anything else, so the parent knows the first signal
arrived before it decides whether to send a second.

It **is** the command: after the two additions above it hands control to
`app.cli`, arguments and all, so the engine, the inference pool, the logging,
the loop, the summary and the disposal under test are the production ones.

Run as `python -m tests.worker_child worker [--once] [--batch N]`, with
`WORKER_BARRIER_DIR` naming a directory both sides can see. Without that
variable it refuses to start: a child with no rendezvous is a test that waits
for nothing.
"""

import asyncio
import os
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from PIL.Image import Image

from app.ml import registry
from app.ml.base import EmbeddingResult
from app.ml.fake import FakeEmbedder
from app.services import indexing
from tests.fake_models import fake_for

#: How long the child will wait at the barrier before giving up. Long enough
#: that a loaded machine does not fail a test, short enough that a test which
#: forgot to release fails instead of hanging for ever.
BARRIER_TIMEOUT_SECONDS = 60.0
POLL_SECONDS = 0.01


def held_marker(directory: Path) -> Path:
    return directory / f"held-{os.getpid()}"


def signalled_marker(directory: Path) -> Path:
    return directory / f"signalled-{os.getpid()}"


def release_marker(directory: Path) -> Path:
    return directory / "release"


def ready_marker(directory: Path) -> Path:
    """Written once the handlers are installed — before it, a signal would find
    the default disposition and kill a process that has claimed nothing."""
    return directory / f"ready-{os.getpid()}"


class HeldEmbedder(FakeEmbedder):
    """The fake, stopped in the middle of the work the runner claimed."""

    def __init__(self, key: str, directory: Path) -> None:
        stand_in = fake_for(key)
        super().__init__(key, stand_in.dim, supports_text=stand_in.supports_text)
        self._directory = directory

    def embed_images(self, images: Sequence[Image]) -> EmbeddingResult:
        held_marker(self._directory).write_text(str(os.getpid()))
        deadline = time.monotonic() + BARRIER_TIMEOUT_SECONDS
        while not release_marker(self._directory).exists():
            if time.monotonic() > deadline:
                raise TimeoutError("the parent never released this child")
            time.sleep(POLL_SECONDS)
        return super().embed_images(images)


def install_held_models(directory: Path) -> None:
    """Every implemented key, faked and held — the registry's own lazy path is
    untouched, only what it builds is ours."""
    registry.clear()
    for key in list(registry.FACTORIES):
        registry.FACTORIES[key] = lambda _settings, key=key: HeldEmbedder(key, directory)


def announce_signals(directory: Path) -> None:
    """Write the acknowledgement before the runner's own policy runs.

    The one seam this harness replaces. Everything else the child does — the
    engine, the inference pool, the logging, the loop, the summary, the
    disposal — is the production command's, so a broken adapter fails these
    tests instead of hiding behind a copy of itself (Gate 2 round 1, finding 2).
    """
    installing = indexing.install_stop_handlers

    def install(
        loop: asyncio.AbstractEventLoop, deliver: Callable[[int], None], **kwargs: object
    ) -> None:
        def acknowledged(number: int) -> None:
            signalled_marker(directory).write_text(str(number))
            deliver(number)

        installing(loop, acknowledged, **kwargs)  # type: ignore[arg-type]
        ready_marker(directory).write_text(str(os.getpid()))

    indexing.install_stop_handlers = install  # type: ignore[assignment]


if __name__ == "__main__":
    named = os.environ.get("WORKER_BARRIER_DIR")
    if not named:
        print("WORKER_BARRIER_DIR is required", file=sys.stderr)
        raise SystemExit(2)

    barrier = Path(named)
    install_held_models(barrier)
    announce_signals(barrier)

    # The production command, with the production argument parsing: the test
    # passes `worker --once` exactly as a terminal would.
    from app.cli import app

    app()
