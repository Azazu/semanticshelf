"""The command line of the service.

One `typer` application, so every operational command lives under one name.
This change adds `models warm`; indexing, the worker and the demo dataset join
it later. Nothing heavy is imported at module level — `--help` must answer
instantly, and the model runtime is pulled in only by the command that needs it.
"""

import asyncio
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Annotated, Any

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


@app.command("index-folder")
def index_folder(
    directory: Annotated[Path, typer.Argument(help="The directory of pictures to import.")],
    recursive: Annotated[
        bool, typer.Option("--recursive", "-r", help="Import subdirectories too.")
    ] = False,
    tags: Annotated[
        str | None, typer.Option("--tags", help="Comma-separated tags for every asset created.")
    ] = None,
    meta: Annotated[
        str | None, typer.Option("--meta", help="A JSON object stored on every asset created.")
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Report what a run would do, and write nothing.")
    ] = False,
    no_index: Annotated[
        bool, typer.Option("--no-index", help="Leave the work queued instead of carrying it out.")
    ] = False,
) -> None:
    """Import a folder of pictures through the same pipeline an upload uses.

    Every file is accepted or refused on its bytes, stored under a generated
    name, and queued for every enabled model. Afterwards the command carries
    out the work it created, unless told to leave it queued, and reports what
    it could not finish.
    """
    from app.services.folder import DirectoryUnusableError
    from app.services.tagging import MetadataError, TagError, parse_metadata, split_tag_fields

    # Values come from the environment; mypy cannot see that the required field is read there.
    settings = Settings()  # type: ignore[call-arg]
    try:
        chosen_tags = split_tag_fields([tags]) if tags else ()
        chosen_meta = parse_metadata(meta)
    except (TagError, MetadataError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    try:
        lines = asyncio.run(
            _run_import(
                settings,
                directory=directory,
                recursive=recursive,
                tags=chosen_tags,
                meta=chosen_meta,
                dry_run=dry_run,
                index=not no_index,
            )
        )
    except (DirectoryUnusableError, TagError, MetadataError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    for line in lines:
        typer.echo(line)


async def _run_import(
    settings: Settings,
    *,
    directory: Path,
    recursive: bool,
    tags: Sequence[str],
    meta: Mapping[str, Any],
    dry_run: bool,
    index: bool,
) -> list[str]:
    from app.db.engine import create_engine, create_session_factory
    from app.ml.pool import create_pool
    from app.services import folder
    from app.storage import MediaStorage

    engine = create_engine(settings)
    pool = create_pool(settings)
    try:
        factory = create_session_factory(engine)
        storage = MediaStorage.at(settings.media_root)
        # A names-only pass first, so the bar has a total. It opens nothing and
        # reads nothing; a tree that changes in between changes the total, not
        # the outcome.
        progress: Any
        total = folder.count_entries(directory, recursive=recursive)
        with typer.progressbar(label="import", length=total) as progress:
            async with factory() as session:
                report = await folder.import_folder(
                    directory,
                    session=session,
                    storage=storage,
                    settings=settings,
                    recursive=recursive,
                    tags=tags,
                    meta=meta,
                    dry_run=dry_run,
                    on_file=lambda _: progress.update(1),
                )
        if index and not dry_run and report.created_assets:
            with typer.progressbar(label="index ", length=len(report.created_assets)) as indexing:
                done = 0

                def advance(finished: int) -> None:
                    nonlocal done
                    indexing.update(max(0, finished - done))
                    done = finished

                await folder.index_imported(
                    report,
                    session_factory=factory,
                    storage=storage,
                    settings=settings,
                    pool=pool,
                    on_progress=advance,
                )
        return folder.describe(report)
    finally:
        pool.shutdown(wait=True)
        await engine.dispose()


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
