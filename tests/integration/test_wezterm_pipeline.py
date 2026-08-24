from __future__ import annotations

import hashlib
import io

import numpy as np

from mojit.adapters.wezterm.backend import WezTermBackend
from mojit.adapters.wezterm.cell_encoder import RESET_COLORS, UPPER_HALF_BLOCK
from mojit.adapters.wezterm.terminal_state import (
    BEGIN_SYNCHRONIZED_UPDATE,
    ENTER_TERMINAL,
    LEAVE_ALTERNATE_SCREEN,
)
from mojit.adapters.wezterm.viewport import PaneGeometry
from mojit.application.request import PreparedRun
from mojit.application.runtime import run_animation
from mojit.core.models import Frame, Orientation, TextMask, Viewport
from mojit.core.typography import TypographyKey


def _geometry(
    width: int,
    height: int,
    *,
    columns: int = 80,
    rows: int = 24,
) -> PaneGeometry:
    return PaneGeometry(2, Viewport(width, height), columns, rows, 96.0)


def test_frame_round_trips_through_cells_and_terminal_lifecycle() -> None:
    rgba = np.array(
        [
            [[255, 0, 0, 255], [0, 255, 0, 128]],
            [[0, 0, 255, 64], [255, 255, 255, 0]],
        ],
        dtype=np.uint8,
    )
    frame = Frame(2, 2, rgba)
    output = io.BytesIO()
    backend = WezTermBackend(
        pane_id=2,
        output=output,
        query_geometry=lambda pane_id: _geometry(2, 2, columns=2, rows=1),
        presentation_pause=0.0,
    )

    backend.preflight()
    backend.enter()
    assert backend.get_viewport() == Viewport(2, 2)
    backend.present(frame)
    backend.restore()

    terminal_bytes = output.getvalue()
    assert terminal_bytes.count(UPPER_HALF_BLOCK) == 2
    assert b"\x1b[38;2;240;0;0;48;2;0;0;64m" in terminal_bytes
    assert b"\x1b[38;2;0;128;0m\x1b[49m" + UPPER_HALF_BLOCK in terminal_bytes
    assert RESET_COLORS in terminal_bytes
    assert terminal_bytes.startswith(ENTER_TERMINAL)
    assert terminal_bytes.endswith(LEAVE_ALTERNATE_SCREEN)
    assert output.closed is False


class AdvancingClock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def _request() -> PreparedRun:
    font_data = b"synthetic-font"
    return PreparedRun(
        text="猫",
        effect_id="pulse",
        orientation=Orientation.HORIZONTAL,
        font_data=font_data,
        font_fingerprint=hashlib.sha256(font_data).hexdigest(),
        fps=30,
        margin=0.08,
        seed=7,
    )


def _rasterize(font_data: bytes, key: TypographyKey) -> TextMask:
    alpha = np.full(
        (key.viewport.height_px, key.viewport.width_px),
        180,
        dtype=np.uint8,
    )
    return TextMask(key.viewport.width_px, key.viewport.height_px, alpha)


def test_runtime_drives_real_wezterm_backend_across_resize() -> None:
    geometries = [_geometry(24, 18), _geometry(28, 20, columns=90, rows=28)]
    query_count = 0

    def query(pane_id: int) -> PaneGeometry:
        nonlocal query_count
        geometry = geometries[min(query_count, len(geometries) - 1)]
        query_count += 1
        return geometry

    output = io.BytesIO()
    backend = WezTermBackend(
        pane_id=2,
        output=output,
        query_geometry=query,
        presentation_pause=0.0,
    )
    presented = 0
    original_present = backend.present

    class CountingBackend:
        def get_viewport(self) -> Viewport | None:
            return backend.get_viewport()

        def present(self, frame: Frame) -> None:
            nonlocal presented
            original_present(frame)
            presented += 1

    backend.preflight()
    backend.enter()
    result = run_animation(
        _request(),
        backend=CountingBackend(),
        clock=AdvancingClock(),
        rasterizer=_rasterize,
        should_stop=lambda: presented == 17,
    )
    backend.restore()

    terminal_bytes = output.getvalue()
    assert result.presented_frames == 17
    assert result.viewport_changes == 1
    assert terminal_bytes.count(BEGIN_SYNCHRONIZED_UPDATE) == 17
    rendered_cells = terminal_bytes.count(UPPER_HALF_BLOCK)
    assert 0 < rendered_cells < 8 * 80 * 24 + 9 * 90 * 28
    assert terminal_bytes.endswith(LEAVE_ALTERNATE_SCREEN)
