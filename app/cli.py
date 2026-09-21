"""The command line of the service.

One `typer` application, so every operational command lives under one name.
This change adds `models warm`; indexing, the worker and the demo dataset join
it later. Nothing heavy is imported at module level — `--help` must answer
instantly, and the model runtime is pulled in only by the command that needs it.
"""

import asyncio
import time
from typing import Annotated

import typer

from app.core.settings import Settings

app = typer.Typer(help="SemanticShelf operations.", no_args_is_help=True)
models_app = typer.Typer(help="Embedding models.", no_args_is_help=True)
app.add_typer(models_app, name="models")
storage_app = typer.Typer(help="The media root.", no_args_is_help=True)
app.add_typer(storage_app, name="storage")


@models_app.command("warm")
def warm() -> None:
    """Load every enabled model, so the first request does not pay for it.

    Downloads the weights into MODEL_CACHE if they are not there yet. Run it in
    the image build or before the service takes traffic.
    """
    from app.ml.registry import get_embedder

    # Values come from the environment; mypy cannot see that the required field is read there.
    settings = Settings()  # type: ignore[call-arg]
    for key in settings.enabled_models:
        started = time.monotonic()
        embedder = get_embedder(key, settings)
        elapsed = time.monotonic() - started
        typer.echo(f"{key}: {embedder.dim} dimensions, loaded in {elapsed:.1f}s")


@storage_app.command("prune")
def prune_storage(
    apply: Annotated[
        bool, typer.Option("--apply", help="Remove what is reported. Without it, nothing changes.")
    ] = False,
) -> None:
    """Reconcile the media root with the store: orphan files, and assets whose
    files are gone.

    Does nothing at all while an upload is in flight — the two are serialised by
    an advisory lock, because an upload between its files and its row looks
    exactly like rubbish left by a crash.
    """
    # Values come from the environment; mypy cannot see that the required field is read there.
    settings = Settings()  # type: ignore[call-arg]
    for line in asyncio.run(_run_prune(settings, apply=apply)):
        typer.echo(line)


async def _run_prune(settings: Settings, *, apply: bool) -> list[str]:
    from app.db.engine import create_engine, create_session_factory
    from app.services.prune import describe, prune
    from app.storage import MediaStorage

    engine = create_engine(settings)
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            report = await prune(
                session,
                MediaStorage.at(settings.media_root),
                min_age_seconds=settings.prune_min_age_seconds,
                apply=apply,
            )
        return describe(report)
    finally:
        await engine.dispose()


if __name__ == "__main__":  # pragma: no cover - the console script is the entry point
    app()
