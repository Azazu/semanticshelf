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
demo_app = typer.Typer(help="The demo corpus.", no_args_is_help=True)
app.add_typer(demo_app, name="demo-dataset")


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
        # The directory is resolved and opened once, here, and everything after
        # this — the count and the import — works from that descriptor. A
        # second resolution would be a second chance for the name to mean
        # something else.
        progress: Any
        with folder.opened_root(directory) as root:
            # A names-only pass first, so the bar has a total. It opens nothing
            # and reads nothing; a tree that changes in between changes the
            # total, not the outcome.
            total = folder.count_entries(root, recursive=recursive)
            with typer.progressbar(label="import", length=total) as progress:
                async with factory() as session:
                    report = await folder.import_folder(
                        root,
                        session=session,
                        storage=storage,
                        settings=settings,
                        recursive=recursive,
                        tags=tags,
                        meta=meta,
                        dry_run=dry_run,
                        on_file=lambda _: progress.update(1),
                    )
        if index and not dry_run:
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


@demo_app.command("download")
def demo_download(
    count: Annotated[int, typer.Option("--count", min=0, help="How many pictures to fetch.")] = 500,
    into: Annotated[Path, typer.Option("--into", help="Where the corpus is built.")] = Path(
        ".data/demo"
    ),
) -> None:
    """Fetch a bounded sample of the demo dataset, with its licences checked.

    The manifest is fetched once and kept; only the pictures whose licence the
    dataset itself declares as permissive are taken; each one is written with a
    sidecar carrying its tags and where it came from. Nothing is stored in the
    service by this command — `demo-dataset index` does that.
    """
    from app.services import demo_dataset

    # Values come from the environment; mypy cannot see that the required field is read there.
    settings = Settings()  # type: ignore[call-arg]
    typer.echo(demo_dataset.licence_notice())
    try:
        with demo_dataset.client() as client:
            report = demo_dataset.download(client, into=into, count=count, settings=settings)
    except (demo_dataset.DownloadError, demo_dataset.ManifestError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    for line in demo_dataset.describe(report):
        typer.echo(line)


@demo_app.command("index")
def demo_index(
    into: Annotated[
        Path, typer.Option("--into", help="The corpus built by `demo-dataset download`.")
    ] = Path(".data/demo"),
) -> None:
    """Import the downloaded corpus through the ordinary folder import.

    The pictures are one directory each, so the import runs recursively over
    `<into>/pictures` — never over the staging area or the archive beside it —
    and finishes the work it created, exactly as `index-folder` does.
    """
    from app.services import demo_dataset

    corpus = demo_dataset.corpus_of(into)
    if not corpus.is_dir():
        typer.echo(f"nothing to index: {corpus} does not exist", err=True)
        raise typer.Exit(code=2)
    index_folder(
        directory=corpus, recursive=True, tags=None, meta=None, dry_run=False, no_index=False
    )


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
