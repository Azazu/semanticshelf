"""`semanticshelf index-folder`: what it prints, and what it exits with.

The command reads its settings from the environment and opens a database, so
these run with the integration suite. What each outcome means is tested in
`test_folder_import.py`; here it is the command's own surface — the options it
accepts, the summary it prints and the status it exits with.
"""

import asyncio
import io
from pathlib import Path

import pytest
import sqlalchemy as sa
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncEngine
from typer.testing import CliRunner, Result

from app.cli import app
from app.core.settings import Settings

pytestmark = pytest.mark.integration

TABLES = "assets, embeddings, indexing_jobs"


def picture_bytes(seed: int = 0) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (400, 200), color=(seed % 255, 90, 200)).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture(autouse=True)
async def empty_store(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(sa.text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))


@pytest.fixture(autouse=True)
def environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, db_settings: Settings) -> None:
    """The command builds its own settings, so the test speaks to it the way an
    operator does: through the environment.

    Every setting the assertions depend on is written here, including which
    models are enabled: inherited, it would be whatever the machine's
    environment file says, and how many units of work a folder creates would
    differ between a laptop and CI.
    """
    media_root = tmp_path / "media"
    media_root.mkdir()
    monkeypatch.setenv("DATABASE_URL", db_settings.database_url)
    monkeypatch.setenv("MEDIA_ROOT", str(media_root))
    monkeypatch.setenv("LOG_LEVEL", "warning")
    monkeypatch.setenv("ENABLED_MODELS", ",".join(db_settings.enabled_models))


@pytest.fixture
def incoming(tmp_path: Path) -> Path:
    directory = tmp_path / "incoming"
    directory.mkdir()
    return directory


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


async def run_cli(runner: CliRunner, *arguments: str) -> Result:
    """The command in a thread of its own.

    It is a synchronous entry point that calls `asyncio.run`, exactly as it
    does in a terminal; the test's own loop must not be the one it finds.
    """
    return await asyncio.to_thread(runner.invoke, app, list(arguments))


async def test_a_run_prints_a_summary_of_every_outcome(runner: CliRunner, incoming: Path) -> None:
    (incoming / "good.png").write_bytes(picture_bytes(seed=1))
    (incoming / "lying.png").write_bytes(b"not a picture at all")
    (incoming / "notes.txt").write_bytes(b"a document")

    result = await run_cli(runner, "index-folder", str(incoming))

    assert result.exit_code == 0, result.output
    assert f"folder: {incoming}" in result.output
    assert "created: 1" in result.output
    assert "refused: 1" in result.output
    assert "skipped: 1" in result.output
    assert "lying.png — the file does not decode as an image" in result.output
    assert "notes.txt — not named like a picture" in result.output
    assert "indexed: 1" in result.output


async def test_a_run_that_refuses_files_still_succeeds(runner: CliRunner, incoming: Path) -> None:
    (incoming / "lying.png").write_bytes(b"not a picture at all")

    result = await run_cli(runner, "index-folder", str(incoming))

    assert result.exit_code == 0, "a refused file is a result, not an error"
    assert "refused: 1" in result.output


async def test_a_directory_that_is_not_there_exits_non_zero(
    runner: CliRunner, tmp_path: Path
) -> None:
    result = await run_cli(runner, "index-folder", str(tmp_path / "nowhere"))

    assert result.exit_code != 0
    assert "no such directory" in result.output


async def test_a_path_that_is_not_a_directory_exits_non_zero(
    runner: CliRunner, tmp_path: Path
) -> None:
    picture = tmp_path / "picture.png"
    picture.write_bytes(picture_bytes())

    result = await run_cli(runner, "index-folder", str(picture))

    assert result.exit_code != 0
    assert "not a directory" in result.output


async def test_a_tag_the_service_refuses_exits_non_zero(runner: CliRunner, incoming: Path) -> None:
    (incoming / "good.png").write_bytes(picture_bytes())

    result = await run_cli(runner, "index-folder", str(incoming), "--tags", "not a tag!")

    assert result.exit_code != 0
    assert "not a tag" in result.output


async def test_metadata_that_is_not_an_object_exits_non_zero(
    runner: CliRunner, incoming: Path
) -> None:
    result = await run_cli(runner, "index-folder", str(incoming), "--meta", "[1, 2]")

    assert result.exit_code != 0
    assert "meta must be a JSON object" in result.output


async def test_the_recursive_option_reaches_the_subdirectories(
    runner: CliRunner, incoming: Path
) -> None:
    (incoming / "trip").mkdir()
    (incoming / "trip" / "deep.png").write_bytes(picture_bytes(seed=3))

    shallow = await run_cli(runner, "index-folder", str(incoming))
    deep = await run_cli(runner, "index-folder", str(incoming), "--recursive")

    assert "created: 0" in shallow.output
    assert "created: 1" in deep.output


async def test_a_dry_run_writes_nothing_and_says_so(
    runner: CliRunner, incoming: Path, engine: AsyncEngine
) -> None:
    (incoming / "good.png").write_bytes(picture_bytes(seed=1))

    result = await run_cli(runner, "index-folder", str(incoming), "--dry-run")

    assert result.exit_code == 0, result.output
    assert "(dry run)" in result.output
    assert "created: 1" in result.output, "what a real run would create"
    async with engine.connect() as connection:
        stored = (await connection.execute(sa.text("SELECT count(*) FROM assets"))).scalar_one()
    assert stored == 0


async def test_no_index_leaves_the_work_queued(
    runner: CliRunner, incoming: Path, engine: AsyncEngine
) -> None:
    (incoming / "good.png").write_bytes(picture_bytes(seed=1))

    result = await run_cli(runner, "index-folder", str(incoming), "--no-index")

    assert result.exit_code == 0, result.output
    assert "indexing: not run" in result.output
    async with engine.connect() as connection:
        status = (
            await connection.execute(sa.text("SELECT status FROM indexing_jobs"))
        ).scalar_one()
        vectors = (
            await connection.execute(sa.text("SELECT count(*) FROM embeddings"))
        ).scalar_one()
    assert (status, vectors) == ("pending", 0)


async def test_tags_and_metadata_reach_the_assets(
    runner: CliRunner, incoming: Path, engine: AsyncEngine
) -> None:
    (incoming / "good.png").write_bytes(picture_bytes(seed=1))

    result = await run_cli(
        runner,
        "index-folder",
        str(incoming),
        "--tags",
        "Dragon, blue",
        "--meta",
        '{"origin": "handbook"}',
    )

    assert result.exit_code == 0, result.output
    async with engine.connect() as connection:
        row = (await connection.execute(sa.text("SELECT tags, meta FROM assets"))).one()
    assert row.tags == ["dragon", "blue"]
    assert row.meta == {"origin": "handbook", "source_path": "good.png"}
