"""Deterministic Pillow-backed encoding of immutable frames as PNG."""

from __future__ import annotations

import io

from PIL import Image

from mojit.adapters.wezterm.errors import PngEncodingError
from mojit.core.models import Frame

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def encode_frame_png(frame: Frame) -> bytes:
    """Encode one complete RGBA frame without retaining or mutating it."""
    if not isinstance(frame, Frame):
        raise TypeError("frame must be a Frame")

    stream = io.BytesIO()
    try:
        image = Image.fromarray(frame.rgba)
        if image.mode != "RGBA" or image.size != (frame.width, frame.height):
            raise PngEncodingError("Pillow did not preserve frame mode and dimensions")
        image.save(stream, format="PNG", compress_level=1, optimize=False)
    except PngEncodingError:
        raise
    except (OSError, TypeError, ValueError) as error:
        raise PngEncodingError(f"PNG encoding failed: {error}") from error

    payload = stream.getvalue()
    if not payload.startswith(PNG_SIGNATURE):
        raise PngEncodingError("PNG encoder returned an invalid payload")
    return payload
