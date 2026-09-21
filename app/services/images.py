"""Deciding what an uploaded file actually is, before anything is decoded.

The order here is the point. A picture's dimensions come from its header, which
costs nothing to read; the pixel cap is applied to those numbers **before** any
pixel is allocated, so a small file claiming an enormous canvas is refused
rather than decoded. Pillow's own bomb guard is configured too, but it is not
what enforces the cap: it warns above its limit and raises only above twice it
(`PIL.Image._decompression_bomb_check`), so the number the requirements name is
enforced here, by comparison.

The thumbnail is re-encoded from the decoded pixels rather than copied or
transformed from the original file, which is what leaves every metadata block
of the original behind — camera data, colour profile, comment, and anything
hidden in one.
"""

import io
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image

if TYPE_CHECKING:  # pragma: no cover - imported for typing only
    from app.core.settings import Settings

#: What the service accepts, as Pillow names it, with what it is stored as.
ACCEPTED_FORMATS: dict[str, tuple[str, str]] = {
    "JPEG": ("image/jpeg", "jpg"),
    "PNG": ("image/png", "png"),
    "WEBP": ("image/webp", "webp"),
}

#: Fixed by the requirements, so they are constants rather than settings: a
#: knob no deployment turns is a knob that rots.
THUMBNAIL_MAX_SIDE = 256
THUMBNAIL_QUALITY = 80


class UndecodableImageError(ValueError):
    """The bytes are not a picture at all."""


class UnsupportedFormatError(ValueError):
    """A picture, but not in a format the service accepts."""


class ImageTooLargeError(ValueError):
    """More pixels than the configured cap allows."""


class ImageTooSmallError(ValueError):
    """Shorter than the configured minimum side."""


@dataclass(frozen=True, slots=True)
class ImageFacts:
    """What the service records about a picture, read from the picture itself."""

    content_type: str
    file_ext: str
    width: int
    height: int


def configure_decoder_guard(settings: "Settings") -> None:
    """Pillow's own guard, as a second line behind `inspect`.

    It is a process-global, which is acceptable for one setting in one process.
    It is not the enforcing check: see this module's docstring.
    """
    Image.MAX_IMAGE_PIXELS = settings.max_image_pixels


def inspect(path: Path, settings: "Settings") -> ImageFacts:
    """What the file is, refusing it before anything is decoded."""
    try:
        with Image.open(path) as image:
            fmt = image.format or ""
            width, height = image.size
    except Image.DecompressionBombError as exc:
        raise ImageTooLargeError(str(exc)) from exc
    except OSError as exc:
        raise UndecodableImageError("the file does not decode as an image") from exc

    if width * height > settings.max_image_pixels:
        raise ImageTooLargeError(
            f"{width * height} pixels exceeds the limit of {settings.max_image_pixels}"
        )
    if fmt not in ACCEPTED_FORMATS:
        raise UnsupportedFormatError(f"unsupported image format: {fmt or 'unknown'}")
    if min(width, height) < settings.min_image_side:
        raise ImageTooSmallError(
            f"the shorter side is {min(width, height)}px, the minimum is {settings.min_image_side}px"
        )

    _verify(path)
    content_type, file_ext = ACCEPTED_FORMATS[fmt]
    return ImageFacts(content_type=content_type, file_ext=file_ext, width=width, height=height)


def _verify(path: Path) -> None:
    """Pillow's integrity check, which consumes the file object it reads."""
    try:
        with Image.open(path) as image:
            image.verify()
    except Exception as exc:  # Pillow raises whatever the decoder raised
        raise UndecodableImageError("the file is not a readable image") from exc


def thumbnail(path: Path) -> bytes:
    """A WebP thumbnail, re-encoded from the decoded pixels.

    Bounded by its longest side, never enlarged: a picture already smaller than
    the bound is kept at its own size rather than blown up into blur.
    """
    with Image.open(path) as image:
        image.load()
        picture = image.convert("RGB")
    picture.thumbnail((THUMBNAIL_MAX_SIDE, THUMBNAIL_MAX_SIDE))
    buffer = io.BytesIO()
    picture.save(buffer, format="WEBP", quality=THUMBNAIL_QUALITY)
    return buffer.getvalue()
