from __future__ import annotations

import numpy as np
import pytest

from mojit.adapters.wezterm import cell_encoder as encoder_module
from mojit.adapters.wezterm.cell_encoder import (
    CLEAR_SCREEN,
    ESC,
    LOWER_HALF_BLOCK,
    RESET_COLORS,
    UPPER_HALF_BLOCK,
    CellEncoder,
    encode_frame_cells,
)
from mojit.adapters.wezterm.errors import CellEncodingError
from mojit.core.models import Frame


def _frame(width: int = 8, height: int = 6) -> Frame:
    rgba = np.arange(width * height * 4, dtype=np.uint8).reshape(height, width, 4)
    return Frame(width, height, rgba)


def test_exact_size_encoding_is_deterministic_and_covers_every_cell() -> None:
    rgba = np.array(
        [
            [[255, 0, 0, 255], [0, 255, 0, 255]],
            [[0, 0, 255, 255], [255, 255, 255, 255]],
        ],
        dtype=np.uint8,
    )
    frame = Frame(2, 2, rgba)

    first = encode_frame_cells(frame, columns=2, rows=1)
    second = encode_frame_cells(frame, columns=2, rows=1)

    assert first == second
    assert first == (
        ESC
        + b"[38;2;255;0;0m"
        + ESC
        + b"[48;2;0;0;255m"
        + UPPER_HALF_BLOCK
        + ESC
        + b"[38;2;0;255;0m"
        + ESC
        + b"[48;2;255;255;255m"
        + UPPER_HALF_BLOCK
        + RESET_COLORS
    )
    assert first.count(UPPER_HALF_BLOCK) == 2
    assert not frame.rgba.flags.writeable


def test_resize_encodes_requested_terminal_geometry() -> None:
    payload = encode_frame_cells(_frame(), columns=5, rows=3)

    assert payload.count(UPPER_HALF_BLOCK) == 15
    assert payload.count(b"\r\n") == 2
    assert payload.endswith(RESET_COLORS)


def test_repeated_colors_do_not_repeat_escape_sequences() -> None:
    rgba = np.zeros((2, 8, 4), dtype=np.uint8)
    rgba[:, :, 3] = 255

    payload = encode_frame_cells(Frame(8, 2, rgba), columns=8, rows=1)

    assert payload.count(ESC + b"[38;2;") == 1
    assert payload.count(ESC + b"[48;2;") == 1
    assert payload.count(UPPER_HALF_BLOCK) == 8


def test_stateful_encoder_emits_only_changed_cells() -> None:
    black = np.zeros((2, 3, 4), dtype=np.uint8)
    black[:, :, 3] = 255
    colored = black.copy()
    colored[:, 1, :3] = [255, 64, 32]
    encoder = CellEncoder()

    initial = encoder(Frame(3, 2, black), columns=3, rows=1)
    changed = encoder(Frame(3, 2, colored), columns=3, rows=1)
    unchanged = encoder(Frame(3, 2, colored), columns=3, rows=1)

    assert initial == CLEAR_SCREEN + RESET_COLORS
    assert changed.endswith(b" \x1b[0m")
    assert b"\x1b[1;2H" in changed
    assert unchanged == RESET_COLORS


def test_stateful_encoder_clears_and_repaints_after_geometry_change() -> None:
    rgba = np.full((2, 2, 4), 255, dtype=np.uint8)
    encoder = CellEncoder()

    encoder(Frame(2, 2, rgba), columns=2, rows=1)
    resized = encoder(Frame(2, 2, rgba), columns=4, rows=2)

    assert resized.startswith(CLEAR_SCREEN)
    assert resized.count(b" ") == 8


def test_stateful_encoder_erases_to_the_terminal_default_background() -> None:
    black = np.zeros((2, 1, 4), dtype=np.uint8)
    black[:, :, 3] = 255
    colored = black.copy()
    colored[:, :, :3] = [255, 64, 32]
    encoder = CellEncoder()

    encoder(Frame(1, 2, colored), columns=1, rows=1)
    erased = encoder(Frame(1, 2, black), columns=1, rows=1)

    assert erased == ESC + b"[1;1H " + RESET_COLORS
    assert b"48;2;0;0;0" not in erased


def test_stateful_encoder_uses_half_blocks_over_the_default_background() -> None:
    rgba = np.zeros((2, 2, 4), dtype=np.uint8)
    rgba[0, 0] = [255, 64, 32, 255]
    rgba[1, 1] = [32, 64, 255, 255]

    payload = CellEncoder()(Frame(2, 2, rgba), columns=2, rows=1)

    assert UPPER_HALF_BLOCK in payload
    assert LOWER_HALF_BLOCK in payload
    assert b"48;2;0;0;0" not in payload


@pytest.mark.parametrize("value", [object(), None, b"frame"])
def test_encoder_rejects_non_frame(value: object) -> None:
    with pytest.raises(TypeError, match="Frame"):
        encode_frame_cells(value, columns=2, rows=1)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("columns", "rows"),
    [(0, 1), (1, 0), (True, 1), (1, 1.5)],
)
def test_encoder_rejects_invalid_cell_geometry(columns: object, rows: object) -> None:
    with pytest.raises(CellEncodingError):
        encode_frame_cells(_frame(), columns=columns, rows=rows)  # type: ignore[arg-type]


def test_encoder_wraps_pillow_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(value: object) -> None:
        del value
        raise OSError("resize unavailable")

    monkeypatch.setattr(encoder_module.Image, "fromarray", fail)
    with pytest.raises(CellEncodingError, match="resize unavailable"):
        encode_frame_cells(_frame(), columns=2, rows=1)
