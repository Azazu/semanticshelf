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
index_app = typer.Typer(help="Work for assets that are already stored.", no_args_is_help=True)
app.add_typer(index_app, name="index")


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

    from app.services.indexing import carries_out_work, queued_because

    # Two instructions, one answer: this run may be told to leave the work
    # queued, and so may the deployment (`INDEXING_RUNNER=worker`).
    left_queued = queued_because(asked_to_leave_it=no_index, settings=settings)
    try:
        lines = asyncio.run(
            _run_import(
                settings,
                directory=directory,
                recursive=recursive,
                tags=chosen_tags,
                meta=chosen_meta,
                dry_run=dry_run,
                index=not no_index and carries_out_work(settings),
            )
        )
    except (DirectoryUnusableError, TagError, MetadataError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    for line in lines:
        typer.echo(line)
    if left_queued is not None and not dry_run:
        typer.echo(left_queued)


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


@index_app.command("missing")
def index_missing(
    model: Annotated[
        str | None,
        typer.Option("--model", help="Only this model. The default is every enabled model."),
    ] = None,
    no_index: Annotated[
        bool, typer.Option("--no-index", help="Leave the work queued instead of carrying it out.")
    ] = False,
) -> None:
    """Queue the work stored assets have none of, and then carry it out.

    What a model that arrived after the pictures needs. An asset is queued when
    it has no vector for that model and no work for it waiting, running or
    failed — so asking twice costs nothing, and work that already gave up is
    passed over and reported rather than quietly retried: `reindex` is what runs
    that again.
    """
    # Values come from the environment; mypy cannot see that the required field is read there.
    settings = Settings()  # type: ignore[call-arg]
    chosen = (model,) if model is not None else settings.enabled_models
    if model is not None and model not in settings.enabled_models:
        typer.echo(
            f"model {model!r} is not enabled in this build; "
            f"enabled: {', '.join(settings.enabled_models) or 'none'}",
            err=True,
        )
        raise typer.Exit(code=2)

    from app.services.indexing import carries_out_work, queued_because

    left_queued = queued_because(asked_to_leave_it=no_index, settings=settings)
    index = not no_index and carries_out_work(settings)
    for line in asyncio.run(_run_backfill(settings, models=chosen, index=index)):
        typer.echo(line)
    if left_queued is not None:
        typer.echo(left_queued)


async def _run_backfill(settings: Settings, *, models: Sequence[str], index: bool) -> list[str]:
    from app.db.engine import create_engine, create_session_factory
    from app.ml.pool import create_pool
    from app.services import indexing
    from app.storage import MediaStorage

    engine = create_engine(settings)
    pool = create_pool(settings)
    reports = []
    try:
        factory = create_session_factory(engine)
        storage = MediaStorage.at(settings.media_root)
        for model in models:
            queued = await indexing.queue_missing(
                session_factory=factory, settings=settings, model=model
            )
            report = indexing.BackfillReport(
                model=model, queued=queued.queued, skipped_failed=queued.skipped_failed
            )
            if index:
                progress: Any
                with typer.progressbar(
                    label=f"index {model}", length=len(queued.queued)
                ) as progress:
                    done = 0

                    def advance(finished: int, progress: Any = progress) -> None:
                        nonlocal done
                        progress.update(max(0, finished - done))
                        done = finished

                    report.work = await indexing.finish_work(
                        queued.queued,
                        session_factory=factory,
                        storage=storage,
                        settings=settings,
                        pool=pool,
                        on_progress=advance,
                    )
            reports.append(report)
        return indexing.describe_backfill(reports)
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


@app.command("worker")
def worker(
    once: Annotated[
        bool, typer.Option("--once", help="Take a single batch, report it, and stop.")
    ] = False,
    batch: Annotated[
        int | None,
        typer.Option("--batch", min=1, help="Jobs per batch, overriding WORKER_BATCH_SIZE."),
    ] = None,
) -> None:
    """Carry out queued indexing work until asked to stop.

    The runner the queue was built for: it claims with `FOR UPDATE SKIP LOCKED`,
    so several of these may run at once with nothing coordinating them, and it
    uses the same claim/execute/finish the API's own runner uses — which is why
    turning it on changes no contract.

    A `SIGTERM` (or `SIGINT`) stops it after the batch it holds: work already
    claimed is finished, nothing new is taken, and nothing is handed back by
    hand — anything it could not finish returns when its lease expires. A second
    signal ends it at once, and that work returns the same way.

    With `INDEXING_RUNNER=worker` this is the only runner: the API and the
    import commands then queue work and execute none of it.
    """
    # Values come from the environment; mypy cannot see that the required field is read there.
    settings = Settings()  # type: ignore[call-arg]
    if batch is not None:
        settings = settings.model_copy(update={"worker_batch_size": batch})
    typer.echo(
        f"worker started: batch {settings.worker_batch_size}, "
        f"poll {settings.worker_poll_seconds}s, "
        f"models {', '.join(settings.enabled_models) or 'none'}"
    )
    typer.echo(asyncio.run(_run_worker(settings, once=once)))


async def _run_worker(settings: Settings, *, once: bool) -> str:
    from app.core.logging import configure_logging
    from app.db.engine import create_engine, create_session_factory
    from app.ml.pool import create_pool
    from app.services import indexing
    from app.storage import MediaStorage

    # Unlike the other commands, this one is a server: it runs until it is
    # stopped, and its log lines are the only way to see what it is doing.
    configure_logging(settings.log_level, settings.log_json)

    engine = create_engine(settings)
    pool = create_pool(settings)
    try:
        stop = indexing.Stop()
        indexing.install_stop_handlers(
            asyncio.get_running_loop(), indexing.StopSignals(stop).deliver
        )
        run = await indexing.run_worker(
            session_factory=create_session_factory(engine),
            storage=MediaStorage.at(settings.media_root),
            settings=settings,
            pool=pool,
            stop=stop,
            once=once,
        )
        return f"worker stopped: {run.batches} batch(es), {run.units} unit(s)"
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
