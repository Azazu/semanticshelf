"""The download: three bounds, no redirects, and a pair that appears at once.

Nothing here reaches the network — every response is served by an
`httpx.MockTransport`, which is also what lets a test say "and then the run made
no further request".
"""

import io
import json
import os
import zipfile
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from PIL import Image

from app.core.settings import Settings
from app.services import demo_dataset
from app.services.demo_dataset import (
    ALREADY_PRESENT,
    ARCHIVE_NAME,
    MANIFEST_MEMBER,
    WRITTEN,
    DownloadError,
    Picture,
    TransferError,
    corpus_of,
    download,
    fetch_archive,
    fetch_picture,
)

PICTURE = Picture(
    identifier=39769,
    licence="http://creativecommons.org/licenses/by/2.0/",
    tags=("cat", "traffic-light"),
)


def picture_bytes(colour: str = "red", size: tuple[int, int] = (64, 64)) -> bytes:
    raw = io.BytesIO()
    Image.new("RGB", size, colour).save(raw, format="PNG")
    return raw.getvalue()


def manifest_archive(images: list[dict[str, object]] | None = None) -> bytes:
    manifest = {
        "licenses": [
            {
                "id": 4,
                "name": "Attribution License",
                "url": "http://creativecommons.org/licenses/by/2.0/",
            }
        ],
        "images": images if images is not None else [{"id": 39769, "license": 4}],
        "categories": [{"id": 1, "name": "cat"}],
        "annotations": [{"image_id": 39769, "category_id": 1}],
    }
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w") as bundle:
        bundle.writestr(MANIFEST_MEMBER, json.dumps(manifest))
    return raw.getvalue()


def client_of(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)


@pytest.fixture
def settings(test_settings: Settings) -> Settings:
    return test_settings


@pytest.fixture
def into(tmp_path: Path) -> Path:
    return tmp_path / "demo"


def serving(**routes: bytes) -> tuple[httpx.Client, list[str]]:
    """A client that answers the named paths, and the log of what it was asked."""
    asked: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(request.url.path)
        for suffix, body in routes.items():
            if request.url.path.endswith(suffix.replace("_", ".")):
                return httpx.Response(200, content=body)
        return httpx.Response(404)

    return client_of(handler), asked


# --- the archive ---------------------------------------------------------------


def test_the_archive_is_fetched_once_and_kept(into: Path) -> None:
    client, asked = serving(zip=manifest_archive())
    into.mkdir(parents=True)

    first = fetch_archive(client, into=into)
    second = fetch_archive(client, into=into)

    assert first == second == into / ARCHIVE_NAME
    assert len(asked) == 1, "the second run asked for nothing"


def test_an_archive_above_its_bound_ends_the_run(
    into: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(demo_dataset, "ARCHIVE_MAX_BYTES", 128)
    client = client_of(lambda request: httpx.Response(200, content=b"x" * 512))
    into.mkdir(parents=True)

    with pytest.raises(DownloadError, match="128"):
        fetch_archive(client, into=into)

    assert not (into / ARCHIVE_NAME).exists()
    assert list((into / ".staging").iterdir()) == [], "the staging file is removed"


def test_an_archive_that_redirects_is_not_followed(into: Path) -> None:
    client = client_of(
        lambda request: httpx.Response(302, headers={"location": "https://elsewhere.example/x"})
    )
    into.mkdir(parents=True)

    with pytest.raises(DownloadError, match="redirect"):
        fetch_archive(client, into=into)

    assert not (into / ARCHIVE_NAME).exists()


def test_an_archive_that_times_out_ends_the_run(into: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow", request=request)

    into.mkdir(parents=True)

    with pytest.raises(DownloadError, match="fetched"):
        fetch_archive(client_of(handler), into=into)

    assert list((into / ".staging").iterdir()) == []


# --- what the client refuses, and what the bounds are ----------------------------


def test_the_client_never_follows_a_redirect() -> None:
    with demo_dataset.client() as made:
        assert made.follow_redirects is False


def test_the_archive_bound_is_not_the_bound_a_picture_has(test_settings: Settings) -> None:
    """Measured on 2026-09-22: the archive COCO publishes is 252 907 541 bytes,
    which is why it cannot be bounded by what a picture may weigh."""
    real_archive = 252_907_541

    assert test_settings.max_upload_bytes < real_archive < demo_dataset.ARCHIVE_MAX_BYTES


def test_a_hostile_file_name_in_the_manifest_is_not_read(
    into: Path, settings: Settings, tmp_path: Path
) -> None:
    """The manifest names its pictures, and this command never reads that name:
    every path is built from the identifier it validated."""
    images = [{"id": 7, "license": 4, "file_name": "../../../../etc/passwd.jpg"}]
    client, _ = serving(zip=manifest_archive(images), jpg=picture_bytes())

    report = download(client, into=into, count=1, settings=settings)

    assert report.written == 1
    assert (corpus_of(into) / "7" / "000000000007.png").is_file()
    assert sorted(entry.name for entry in tmp_path.iterdir()) == ["demo"]


# --- one picture ----------------------------------------------------------------


def test_a_picture_and_its_sidecar_are_published_together(into: Path, settings: Settings) -> None:
    client, _ = serving(jpg=picture_bytes())

    assert fetch_picture(client, PICTURE, into=into, settings=settings) == WRITTEN

    directory = corpus_of(into) / "39769"
    assert sorted(entry.name for entry in directory.iterdir()) == [
        "000000039769.json",
        "000000039769.png",
    ]
    sidecar = json.loads((directory / "000000039769.json").read_text())
    assert sidecar["tags"] == ["cat", "traffic-light"]
    assert sidecar["meta"]["dataset_id"] == "39769"
    assert "author" not in sidecar["meta"]


def test_the_name_comes_from_the_identifier_and_the_decoded_bytes(
    into: Path, settings: Settings
) -> None:
    """A JPEG served for a picture COCO names `.jpg` still lands under the
    extension its bytes earned, and under the identifier this command validated."""
    client, asked = serving(jpg=picture_bytes())

    fetch_picture(client, PICTURE, into=into, settings=settings)

    assert (corpus_of(into) / "39769" / "000000039769.png").is_file()
    assert asked == ["/images.cocodataset.org/val2017/000000039769.jpg"]


def test_a_picture_above_the_upload_bound_leaves_nothing(into: Path, settings: Settings) -> None:
    small = settings.model_copy(update={"max_upload_bytes": 64})
    client, _ = serving(jpg=picture_bytes(size=(256, 256)))

    with pytest.raises(TransferError, match="64"):
        fetch_picture(client, PICTURE, into=into, settings=small)

    assert not (corpus_of(into) / "39769").exists()
    assert list((into / ".staging").iterdir()) == [], "the staging directory is gone"


def test_a_picture_that_redirects_is_not_followed(into: Path, settings: Settings) -> None:
    client = client_of(
        lambda request: httpx.Response(301, headers={"location": "https://elsewhere.example/x"})
    )

    with pytest.raises(TransferError, match="redirect"):
        fetch_picture(client, PICTURE, into=into, settings=settings)

    assert not (corpus_of(into) / "39769").exists()


def test_a_picture_that_does_not_answer_in_time_is_abandoned(
    into: Path, settings: Settings
) -> None:
    """A slow picture costs one timeout, not the run."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow", request=request)

    with pytest.raises(httpx.ReadTimeout):
        fetch_picture(client_of(handler), PICTURE, into=into, settings=settings)

    assert not (corpus_of(into) / "39769").exists()
    assert list((into / ".staging").iterdir()) == []


def test_bytes_that_are_not_a_picture_are_discarded(into: Path, settings: Settings) -> None:
    client, _ = serving(jpg=b"this is not an image")

    with pytest.raises(Exception) as refusal:
        fetch_picture(client, PICTURE, into=into, settings=settings)

    assert isinstance(refusal.value, demo_dataset.REFUSALS)
    assert not (corpus_of(into) / "39769").exists()
    assert list((into / ".staging").iterdir()) == []


def test_a_picture_already_present_is_not_fetched_again(into: Path, settings: Settings) -> None:
    client, asked = serving(jpg=picture_bytes())
    fetch_picture(client, PICTURE, into=into, settings=settings)

    assert fetch_picture(client, PICTURE, into=into, settings=settings) == ALREADY_PRESENT
    assert len(asked) == 1


def test_a_failure_before_the_rename_leaves_the_corpus_untouched(
    into: Path, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The publication is the rename; everything before it is invisible."""
    client, _ = serving(jpg=picture_bytes())
    monkeypatch.setattr(demo_dataset, "sidecar_of", lambda picture: 1 / 0)

    with pytest.raises(ZeroDivisionError):
        fetch_picture(client, PICTURE, into=into, settings=settings)

    assert not corpus_of(into).exists()
    assert list((into / ".staging").iterdir()) == []


def test_the_pair_is_published_by_one_rename_of_a_directory(
    into: Path, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The mechanism itself, because the guarantee is the mechanism: at the
    moment of publication there is exactly one rename, and it moves a directory
    holding both files."""
    client, _ = serving(jpg=picture_bytes())
    renames: list[tuple[str, str]] = []
    real_rename = os.rename

    def watched(source: object, destination: object) -> None:
        renames.append((str(source), str(destination)))
        real_rename(source, destination)  # type: ignore[arg-type]

    monkeypatch.setattr(demo_dataset.os, "rename", watched)
    fetch_picture(client, PICTURE, into=into, settings=settings)

    publication = [pair for pair in renames if pair[1].endswith("pictures/39769")]
    assert len(publication) == 1
    source = Path(publication[0][0])
    assert source.parent.name == ".staging"


# --- a whole run ------------------------------------------------------------------


def test_a_run_reports_what_it_did(into: Path, settings: Settings) -> None:
    client, _ = serving(zip=manifest_archive(), jpg=picture_bytes())

    report = download(client, into=into, count=1, settings=settings)

    assert (report.written, report.already_present, report.failed) == (1, 0, 0)
    assert report.refused_for_licence == 0


def test_a_count_of_zero_writes_nothing_but_still_reads_the_manifest(
    into: Path, settings: Settings
) -> None:
    client, asked = serving(zip=manifest_archive(), jpg=picture_bytes())

    report = download(client, into=into, count=0, settings=settings)

    assert report.written == 0
    assert [path for path in asked if path.endswith(".jpg")] == []
    assert not corpus_of(into).exists()


def test_the_count_bounds_what_is_written(into: Path, settings: Settings) -> None:
    images = [{"id": identifier, "license": 4} for identifier in (1, 2, 3, 4)]
    client, asked = serving(zip=manifest_archive(images), jpg=picture_bytes())

    report = download(client, into=into, count=2, settings=settings)

    assert report.written == 2
    assert len([path for path in asked if path.endswith(".jpg")]) == 2


def test_a_picture_that_fails_is_counted_and_the_run_goes_on(
    into: Path, settings: Settings
) -> None:
    images = [{"id": identifier, "license": 4} for identifier in (1, 2)]
    archive = manifest_archive(images)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(".zip"):
            return httpx.Response(200, content=archive)
        if request.url.path.endswith("000000000001.jpg"):
            return httpx.Response(503)
        return httpx.Response(200, content=picture_bytes())

    report = download(client_of(handler), into=into, count=2, settings=settings)

    assert (report.written, report.failed) == (1, 1)
    assert report.failures and report.failures[0].startswith("1: ")


def test_a_picture_refused_for_its_licence_is_never_requested(
    into: Path, settings: Settings
) -> None:
    images = [{"id": 1, "license": 2}, {"id": 2, "license": 4}]
    client, asked = serving(zip=manifest_archive(images), jpg=picture_bytes())

    report = download(client, into=into, count=5, settings=settings)

    assert (report.written, report.refused_for_licence) == (1, 1)
    assert [path for path in asked if path.endswith(".jpg")] == [
        "/images.cocodataset.org/val2017/000000000002.jpg"
    ]


def test_two_runs_racing_publish_one_run_s_pair_and_never_a_mixture(
    into: Path, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The interleaving the first Gate 1 confirmation named, with runs that can
    be told apart.

    Both runs stage a complete pair before either publishes — red serves a red
    picture tagged `red`, blue a blue one tagged `blue` — and the blue run
    publishes *in the middle of* the red run's publication. A scheme that moves
    the two files one at a time pairs one run's picture with the other's
    sidecar here; moving the directory cannot, so whichever run publishes first
    owns both halves.
    """
    red_run = Picture(identifier=7, licence=PICTURE.licence, tags=("red",))
    blue_run = Picture(identifier=7, licence=PICTURE.licence, tags=("blue",))
    red, blue = picture_bytes("red"), picture_bytes("blue")
    red_client, _ = serving(jpg=red)
    blue_client, _ = serving(jpg=blue)

    red_staging = demo_dataset.stage(red_client, red_run, into=into, settings=settings)
    blue_staging = demo_dataset.stage(blue_client, blue_run, into=into, settings=settings)
    assert not corpus_of(into).exists(), "staging is invisible until it is published"

    real_rename = os.rename
    blue_outcome: list[str] = []

    def blue_publishes_in_between(source: object, destination: object) -> None:
        real_rename(source, destination)  # type: ignore[arg-type]
        if "pictures" in str(destination) and not blue_outcome:
            monkeypatch.setattr(demo_dataset.os, "rename", real_rename)
            blue_outcome.append(demo_dataset.publish(blue_staging, into=into, identifier=7))
            monkeypatch.setattr(demo_dataset.os, "rename", blue_publishes_in_between)

    monkeypatch.setattr(demo_dataset.os, "rename", blue_publishes_in_between)

    red_outcome = demo_dataset.publish(red_staging, into=into, identifier=7)

    directory = corpus_of(into) / "7"
    written = (directory / "000000000007.png").read_bytes()
    sidecar = json.loads((directory / "000000000007.json").read_text())
    assert (red_outcome, blue_outcome) == (WRITTEN, [ALREADY_PRESENT])
    assert written == red, "the picture belongs to the run that published first"
    assert sidecar["tags"] == ["red"], "and so does the sidecar: the pair moved together"
    assert list((into / ".staging").iterdir()) == [], "the loser cleaned up after itself"


def test_two_runs_one_after_the_other_leave_the_first_pair_alone(
    into: Path, settings: Settings
) -> None:
    red_run = Picture(identifier=7, licence=PICTURE.licence, tags=("red",))
    blue_run = Picture(identifier=7, licence=PICTURE.licence, tags=("blue",))
    red, blue = picture_bytes("red"), picture_bytes("blue")
    red_client, _ = serving(jpg=red)
    blue_client, asked = serving(jpg=blue)

    first = fetch_picture(red_client, red_run, into=into, settings=settings)
    second = fetch_picture(blue_client, blue_run, into=into, settings=settings)

    directory = corpus_of(into) / "7"
    assert (first, second) == (WRITTEN, ALREADY_PRESENT)
    assert (directory / "000000000007.png").read_bytes() == red
    assert json.loads((directory / "000000000007.json").read_text())["tags"] == ["red"]
    assert asked == [], "the second run asked for nothing"
