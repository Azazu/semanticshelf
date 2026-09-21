"""What an uploaded file is, and what is refused before anything is decoded."""

import io
from pathlib import Path

import pytest
from PIL import Image

from app.core.settings import Settings
from app.services.images import (
    THUMBNAIL_MAX_SIDE,
    ImageTooLargeError,
    ImageTooSmallError,
    UndecodableImageError,
    UnsupportedFormatError,
    configure_decoder_guard,
    inspect,
    thumbnail,
)

VALID_URL = "postgresql+asyncpg://localhost/semanticshelf"


@pytest.fixture
def settings() -> Settings:
    return Settings(  # type: ignore[call-arg]
        _env_file=None, database_url=VALID_URL, max_image_pixels=10_000, min_image_side=32
    )


def picture(tmp_path: Path, name: str, size: tuple[int, int], fmt: str, **save: object) -> Path:
    path = tmp_path / name
    Image.new("RGB", size, color=(200, 30, 30)).save(path, format=fmt, **save)
    return path


@pytest.mark.parametrize(
    ("fmt", "content_type", "file_ext"),
    [("JPEG", "image/jpeg", "jpg"), ("PNG", "image/png", "png"), ("WEBP", "image/webp", "webp")],
)
def test_each_accepted_format_is_read_from_the_bytes(
    tmp_path: Path, settings: Settings, fmt: str, content_type: str, file_ext: str
) -> None:
    path = picture(tmp_path, f"p.{fmt.lower()}", (64, 48), fmt)

    facts = inspect(path, settings)

    assert facts.content_type == content_type
    assert facts.file_ext == file_ext
    assert (facts.width, facts.height) == (64, 48)


def test_the_name_and_the_declared_type_do_not_matter(tmp_path: Path, settings: Settings) -> None:
    # A PNG called .jpg: the bytes decide, and the bytes say PNG.
    path = picture(tmp_path, "misleading.jpg", (64, 64), "PNG")

    assert inspect(path, settings).content_type == "image/png"


def test_a_format_the_service_does_not_accept_is_refused(
    tmp_path: Path, settings: Settings
) -> None:
    path = picture(tmp_path, "picture.bmp", (64, 64), "BMP")

    with pytest.raises(UnsupportedFormatError, match="BMP"):
        inspect(path, settings)


def test_a_file_that_is_not_a_picture_is_refused(tmp_path: Path, settings: Settings) -> None:
    path = tmp_path / "notes.txt"
    path.write_bytes(b"this is not a picture")

    with pytest.raises(UndecodableImageError):
        inspect(path, settings)


def test_a_truncated_picture_is_refused(tmp_path: Path, settings: Settings) -> None:
    whole = picture(tmp_path, "whole.png", (64, 64), "PNG").read_bytes()
    path = tmp_path / "truncated.png"
    path.write_bytes(whole[: len(whole) // 2])

    with pytest.raises(UndecodableImageError):
        inspect(path, settings)


def test_the_pixel_cap_is_enforced_at_the_number_it_names(
    tmp_path: Path, settings: Settings
) -> None:
    # 100 x 100 is exactly the cap of this configuration; 101 x 100 is over it.
    at_cap = picture(tmp_path, "at-cap.png", (100, 100), "PNG")
    over_cap = picture(tmp_path, "over-cap.png", (101, 100), "PNG")

    assert inspect(at_cap, settings).width == 100
    with pytest.raises(ImageTooLargeError, match="10100"):
        inspect(over_cap, settings)


def test_a_bomb_is_refused_from_its_header(tmp_path: Path, settings: Settings) -> None:
    # A tiny file declaring an enormous canvas: refused on its header, so the
    # pixels are never allocated.
    path = picture(tmp_path, "bomb.png", (4000, 4000), "PNG")
    assert path.stat().st_size < 100_000

    with pytest.raises(ImageTooLargeError):
        inspect(path, settings)


def test_a_picture_under_the_minimum_side_is_refused(tmp_path: Path, settings: Settings) -> None:
    path = picture(tmp_path, "tiny.png", (31, 64), "PNG")

    with pytest.raises(ImageTooSmallError, match="31"):
        inspect(path, settings)


def test_the_decoder_guard_is_configured_from_the_setting(settings: Settings) -> None:
    configure_decoder_guard(settings)
    assert Image.MAX_IMAGE_PIXELS == settings.max_image_pixels


def test_the_thumbnail_is_bounded_and_keeps_its_proportions(tmp_path: Path) -> None:
    path = picture(tmp_path, "wide.jpg", (800, 400), "JPEG")

    data = thumbnail(path)

    with Image.open(io.BytesIO(data)) as thumb:
        assert thumb.format == "WEBP"
        assert max(thumb.size) == THUMBNAIL_MAX_SIDE
        assert thumb.size == (THUMBNAIL_MAX_SIDE, THUMBNAIL_MAX_SIDE // 2)


def test_the_thumbnail_carries_nothing_over_from_the_original(tmp_path: Path) -> None:
    path = tmp_path / "with-metadata.jpg"
    marker = b"the-original-carried-this"
    Image.new("RGB", (400, 300), color=(10, 200, 10)).save(
        path, format="JPEG", comment=marker, exif=Image.Exif().tobytes()
    )
    assert marker in path.read_bytes()

    data = thumbnail(path)

    assert marker not in data
    with Image.open(io.BytesIO(data)) as thumb:
        assert not thumb.info.get("exif")
        assert not thumb.info.get("comment")


def test_the_application_factory_configures_the_guard(settings: Settings) -> None:
    from app.main import create_app

    Image.MAX_IMAGE_PIXELS = 1
    create_app(settings)

    assert Image.MAX_IMAGE_PIXELS == settings.max_image_pixels


def test_a_picture_smaller_than_the_bound_keeps_its_own_size(tmp_path: Path) -> None:
    # Accepted sources start at 32px, so this is ordinary rather than exotic:
    # the thumbnail is bounded, never enlarged (FR-AST-6).
    path = picture(tmp_path, "small.png", (64, 48), "PNG")

    data = thumbnail(path)

    with Image.open(io.BytesIO(data)) as thumb:
        assert thumb.size == (64, 48)
        assert thumb.format == "WEBP"


def test_a_file_that_is_not_there_is_not_called_undecodable(
    tmp_path: Path, settings: Settings
) -> None:
    """The indexing service tells a missing original from a broken one, and it
    can only do that if the inspection keeps them apart."""
    with pytest.raises(FileNotFoundError):
        inspect(tmp_path / "gone.png", settings)
