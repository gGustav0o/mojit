"""Deterministic truecolor half-block encoding for terminal cells."""

from __future__ import annotations

import numpy as np
from PIL import Image

from mojit.adapters.wezterm.errors import CellEncodingError
from mojit.core.models import Frame

ESC = b"\x1b"
RESET_COLORS = ESC + b"[0m"
UPPER_HALF_BLOCK = "▀".encode()
LOWER_HALF_BLOCK = "▄".encode()
CLEAR_SCREEN = ESC + b"[2J"
COLOR_MASK = np.uint8(0xF0)
BLACK = (0, 0, 0)


def _require_dimension(value: object, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise CellEncodingError(f"{name} must be a positive integer")
    return value


def _sample_frame(frame: Frame, *, columns: int, rows: int) -> np.ndarray:
    if not isinstance(frame, Frame):
        raise TypeError("frame must be a Frame")
    cell_columns = _require_dimension(columns, name="columns")
    cell_rows = _require_dimension(rows, name="rows")

    try:
        source = Image.fromarray(frame.rgba)
        if source.mode != "RGBA" or source.size != (frame.width, frame.height):
            raise CellEncodingError("Pillow did not preserve frame mode and dimensions")
        background = Image.new("RGBA", source.size, (0, 0, 0, 255))
        background.alpha_composite(source)
        resized = background.convert("RGB").resize(
            (cell_columns, cell_rows * 2),
            Image.Resampling.LANCZOS,
        )
        pixels = np.array(resized, dtype=np.uint8, copy=True)
        return pixels.reshape(cell_rows, 2, cell_columns, 3).transpose(0, 2, 1, 3)
    except (OSError, TypeError, ValueError) as error:
        raise CellEncodingError(f"cell encoding failed: {error}") from error


def _append_cell(
    output: bytearray,
    cell: np.ndarray,
    previous_top: tuple[int, int, int] | None,
    previous_bottom: tuple[int, int, int] | None,
) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    top = tuple(int(value) for value in cell[0])
    bottom = tuple(int(value) for value in cell[1])
    if top != previous_top:
        output.extend(f"\x1b[38;2;{top[0]};{top[1]};{top[2]}m".encode())
    if bottom != previous_bottom:
        output.extend(f"\x1b[48;2;{bottom[0]};{bottom[1]};{bottom[2]}m".encode())
    output.extend(UPPER_HALF_BLOCK)
    return top, bottom


def _append_changed_cell(
    output: bytearray,
    cell: np.ndarray,
    foreground: tuple[int, int, int] | None,
    background: tuple[int, int, int] | None,
) -> tuple[tuple[int, int, int] | None, tuple[int, int, int]]:
    top = tuple(int(value) for value in cell[0])
    bottom = tuple(int(value) for value in cell[1])
    if top == BLACK and bottom == BLACK:
        if background is not None:
            output.extend(ESC + b"[49m")
        output.extend(b" ")
        return foreground, None

    if top == bottom:
        if bottom != background:
            output.extend(f"\x1b[48;2;{bottom[0]};{bottom[1]};{bottom[2]}m".encode())
        output.extend(b" ")
        return foreground, bottom


    if top == BLACK or bottom == BLACK:
        color = bottom if top == BLACK else top
        if color != foreground:
            output.extend(f"\x1b[38;2;{color[0]};{color[1]};{color[2]}m".encode())
        if background is not None:
            output.extend(ESC + b"[49m")
        output.extend(LOWER_HALF_BLOCK if top == BLACK else UPPER_HALF_BLOCK)
        return color, None

    if top != foreground and bottom != background:
        output.extend(
            f"\x1b[38;2;{top[0]};{top[1]};{top[2]};"
            f"48;2;{bottom[0]};{bottom[1]};{bottom[2]}m".encode()
        )
    elif top != foreground:
        output.extend(f"\x1b[38;2;{top[0]};{top[1]};{top[2]}m".encode())
    elif bottom != background:
        output.extend(f"\x1b[48;2;{bottom[0]};{bottom[1]};{bottom[2]}m".encode())
    output.extend(UPPER_HALF_BLOCK)
    return top, bottom


def encode_frame_cells(frame: Frame, *, columns: int, rows: int) -> bytes:
    """Downsample an RGBA frame into a complete truecolor half-block image."""
    cells = _sample_frame(frame, columns=columns, rows=rows)

    output = bytearray()
    previous_top: tuple[int, int, int] | None = None
    previous_bottom: tuple[int, int, int] | None = None
    for row in range(cells.shape[0]):
        if row:
            output.extend(b"\r\n")
        for column in range(cells.shape[1]):
            previous_top, previous_bottom = _append_cell(
                output,
                cells[row, column],
                previous_top,
                previous_bottom,
            )
    output.extend(RESET_COLORS)
    return bytes(output)


class CellEncoder:
    """Encode only cells whose quantized colors changed since the last frame."""

    __slots__ = ("_geometry", "_previous")

    def __init__(self) -> None:
        self._geometry: tuple[int, int] | None = None
        self._previous: np.ndarray | None = None

    def __call__(self, frame: Frame, *, columns: int, rows: int) -> bytes:
        cells = _sample_frame(frame, columns=columns, rows=rows)
        cells &= COLOR_MASK
        geometry = (columns, rows)
        reset = self._geometry != geometry or self._previous is None
        if reset:
            changed = np.any(cells != 0, axis=(2, 3))
        else:
            changed = np.any(cells != self._previous, axis=(2, 3))

        output = bytearray(CLEAR_SCREEN if reset else b"")
        foreground: tuple[int, int, int] | None = None
        background: tuple[int, int, int] | None = None
        for row in range(rows):
            columns_changed = np.flatnonzero(changed[row])
            if columns_changed.size == 0:
                continue
            run_start = 0
            while run_start < columns_changed.size:
                run_end = run_start + 1
                while (
                    run_end < columns_changed.size
                    and columns_changed[run_end] == columns_changed[run_end - 1] + 1
                ):
                    run_end += 1
                first_column = int(columns_changed[run_start])
                output.extend(f"\x1b[{row + 1};{first_column + 1}H".encode())
                for changed_column in columns_changed[run_start:run_end]:
                    foreground, background = _append_changed_cell(
                        output,
                        cells[row, int(changed_column)],
                        foreground,
                        background,
                    )
                run_start = run_end

        output.extend(RESET_COLORS)
        self._geometry = geometry
        self._previous = cells
        return bytes(output)
