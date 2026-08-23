from __future__ import annotations

import io

import numpy as np
import pytest
from PIL import Image

from mojit.adapters.wezterm import png_encoder as encoder_module
from mojit.adapters.wezterm.errors import PngEncodingError
from mojit.adapters.wezterm.png_encoder import PNG_SIGNATURE, encode_frame_png
from mojit.core.models import Frame


def _frame() -> Frame:
    rgba = np.arange(6 * 8 * 4, dtype=np.uint8).reshape(6, 8, 4)
    return Frame(8, 6, rgba)


def test_png_round_trip_preserves_exact_rgba_and_is_deterministic() -> None:
    frame = _frame()
    first = encode_frame_png(frame)
    second = encode_frame_png(frame)

    assert first == second
    assert first.startswith(PNG_SIGNATURE)
    with Image.open(io.BytesIO(first)) as decoded:
        assert decoded.mode == "RGBA"
        assert decoded.size == (8, 6)
        assert np.array_equal(np.asarray(decoded), frame.rgba)
    assert not frame.rgba.flags.writeable


def test_png_encoder_rejects_non_frame() -> None:
    with pytest.raises(TypeError, match="Frame"):
        encode_frame_png(object())  # type: ignore[arg-type]


def test_png_encoder_wraps_pillow_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(value: object) -> None:
        del value
        raise OSError("codec unavailable")

    monkeypatch.setattr(encoder_module.Image, "fromarray", fail)
    with pytest.raises(PngEncodingError, match="codec unavailable"):
        encode_frame_png(_frame())


def test_png_encoder_rejects_changed_pillow_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    class WrongImage:
        mode = "RGB"
        size = (8, 6)

    monkeypatch.setattr(encoder_module.Image, "fromarray", lambda value: WrongImage())
    with pytest.raises(PngEncodingError, match="preserve"):
        encode_frame_png(_frame())
