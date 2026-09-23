"""The `demo-dataset` commands: what they print, and what they refuse.

The transport is stubbed, so nothing here reaches the network; the database is
the unreachable one, which is also the proof that `download` never touches it.
"""

import io
import json
import re
import zipfile
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from PIL import Image
from typer.testing import CliRunner

from app.cli import app
from app.services import demo_dataset
from app.services.demo_dataset import MANIFEST_MEMBER
from tests.conftest import UNREACHABLE_DATABASE_URL


@pytest.fixture(autouse=True)
def environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The commands read their settings from the environment, as they do in a
    terminal; nothing here depends on a file in the repository."""
    monkeypatch.setenv("DATABASE_URL", UNREACHABLE_DATABASE_URL)
    monkeypatch.setenv("MEDIA_ROOT", str(tmp_path / "media"))


def picture_bytes() -> bytes:
    raw = io.BytesIO()
    Image.new("RGB", (64, 64), "red").save(raw, format="PNG")
    return raw.getvalue()


def archive_bytes(count: int = 2) -> bytes:
    manifest = {
        "licenses": [
            {
                "id": 4,
                "name": "Attribution License",
                "url": "http://creativecommons.org/licenses/by/2.0/",
            },
            {
                "id": 2,
                "name": "Attribution-NonCommercial License",
                "url": "http://creativecommons.org/licenses/by-nc/2.0/",
            },
        ],
        "images": [{"id": index + 1, "license": 4} for index in range(count)]
        + [{"id": 900, "license": 2}],
        "categories": [{"id": 1, "name": "traffic light"}],
        "annotations": [{"image_id": 1, "category_id": 1}],
    }
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w") as bundle:
        bundle.writestr(MANIFEST_MEMBER, json.dumps(manifest))
    return raw.getvalue()


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """Every request the commands make, answered from memory and recorded."""
    asked: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(request.url.path)
        if request.url.path.endswith(".zip"):
            return httpx.Response(200, content=archive_bytes())
        return httpx.Response(200, content=picture_bytes())

    def client() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)

    monkeypatch.setattr(demo_dataset, "client", client)
    yield asked


#: Rich styles an option name in pieces — `--count` is rendered as a styled `-`
#: followed by a styled `-count` — so the literal never appears in a coloured
#: help text. CI turns colour on (`FORCE_COLOR`) and a developer's terminal
#: usually does not, which is exactly the difference that let this pass here and
#: fail there. The escapes are stripped, and colour is turned off as well, so
#: what is asserted is the text rather than the styling.
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def run(*arguments: str) -> tuple[int, str]:
    result = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb"}).invoke(app, list(arguments))
    return result.exit_code, ANSI.sub("", result.output)


def test_a_download_prints_the_notice_and_what_it_did(served: list[str], tmp_path: Path) -> None:
    code, output = run("demo-dataset", "download", "--count", "2", "--into", str(tmp_path / "demo"))

    assert code == 0
    assert "creativecommons.org/licenses/by/2.0" in output
    assert "Attribution is by address" in output
    assert "written:            2" in output
    assert "refused (licence):  1" in output


def test_the_notice_is_printed_even_when_nothing_is_downloaded(
    served: list[str], tmp_path: Path
) -> None:
    code, output = run("demo-dataset", "download", "--count", "0", "--into", str(tmp_path / "demo"))

    assert code == 0
    assert "creativecommons.org" in output
    assert "written:            0" in output
    assert [path for path in served if path.endswith(".jpg")] == []


def test_a_download_writes_a_pair_per_picture(served: list[str], tmp_path: Path) -> None:
    into = tmp_path / "demo"

    run("demo-dataset", "download", "--count", "1", "--into", str(into))

    directory = into / "pictures" / "1"
    assert sorted(entry.name for entry in directory.iterdir()) == [
        "000000000001.json",
        "000000000001.png",
    ]
    sidecar = json.loads((directory / "000000000001.json").read_text())
    assert sidecar["tags"] == ["traffic-light"], "the label became a tag"
    assert sidecar["meta"]["licence"] == "http://creativecommons.org/licenses/by/2.0/"


def test_a_second_download_asks_for_nothing_it_already_has(
    served: list[str], tmp_path: Path
) -> None:
    into = tmp_path / "demo"
    run("demo-dataset", "download", "--count", "2", "--into", str(into))
    asked_first = len(served)

    code, output = run("demo-dataset", "download", "--count", "2", "--into", str(into))

    assert code == 0
    assert "already present:    2" in output
    assert len(served) == asked_first, "neither the archive nor a picture was fetched again"


def test_a_failing_archive_ends_the_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def refusing() -> httpx.Client:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500)

        return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)

    monkeypatch.setattr(demo_dataset, "client", refusing)

    code, output = run("demo-dataset", "download", "--into", str(tmp_path / "demo"))

    assert code == 2
    assert "manifest archive" in output


def test_indexing_a_corpus_that_is_not_there_says_so(tmp_path: Path) -> None:
    code, output = run("demo-dataset", "index", "--into", str(tmp_path / "nothing"))

    assert code == 2
    assert "nothing to index" in output


def test_indexing_hands_the_corpus_to_the_ordinary_import(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """One directory per picture, so the import runs recursively — and over the
    corpus alone, never over the staging area or the archive beside it."""
    into = tmp_path / "demo"
    (into / "pictures" / "1").mkdir(parents=True)
    (into / ".staging").mkdir()
    given: dict[str, object] = {}

    def record(**arguments: object) -> None:
        given.update(arguments)

    monkeypatch.setattr("app.cli.index_folder", record)

    code, _ = run("demo-dataset", "index", "--into", str(into))

    assert code == 0
    assert given["directory"] == into / "pictures"
    assert given["recursive"] is True
    assert given["dry_run"] is False and given["no_index"] is False


def test_the_commands_are_documented_in_the_help() -> None:
    _, top = run("demo-dataset", "--help")
    _, download = run("demo-dataset", "download", "--help")

    assert "download" in top and "index" in top
    assert "--count" in download and "--into" in download
