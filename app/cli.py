"""The command line of the service.

One `typer` application, so every operational command lives under one name.
This change adds `models warm`; indexing, the worker and the demo dataset join
it later. Nothing heavy is imported at module level — `--help` must answer
instantly, and the model runtime is pulled in only by the command that needs it.
"""

import time

import typer

from app.core.settings import Settings

app = typer.Typer(help="SemanticShelf operations.", no_args_is_help=True)
models_app = typer.Typer(help="Embedding models.", no_args_is_help=True)
app.add_typer(models_app, name="models")


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


if __name__ == "__main__":  # pragma: no cover - the console script is the entry point
    app()
