from __future__ import annotations

import hashlib

import numpy as np

from mojit.adapters.wezterm.backend import WezTermBackend
from mojit.adapters.wezterm.cell_encoder import ESC, RESET_COLORS
from mojit.adapters.wezterm.errors import ViewportQueryError
from mojit.adapters.wezterm.viewport import PaneGeometry
from mojit.application.request import PreparedRun
from mojit.application.runtime import run_animation
from mojit.core.models import Orientation, TextMask, Viewport
from mojit.core.typography import TypographyKey


class CountingOutput:
    __slots__ = ("flushes", "max_write", "total_bytes", "writes")

    def __init__(self) -> None:
        self.total_bytes = 0
        self.max_write = 0
        self.writes = 0
        self.flushes = 0

    def write(self, value: bytes | memoryview) -> int:
        size = len(value)
        self.total_bytes += size
        self.max_write = max(self.max_write, size)
        self.writes += 1
        return size

    def flush(self) -> None:
        self.flushes += 1


class AdvancingClock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def test_transport_state_remains_bounded_across_one_thousand_frames() -> None:
    output = CountingOutput()
    query_calls = 0
    encoded_frames = 0

    def query(pane_id: int) -> PaneGeometry:
        nonlocal query_calls
        query_calls += 1
        if query_calls > 1 and query_calls % 7 == 0:
            raise ViewportQueryError("transient")
        return PaneGeometry(
            pane_id,
            Viewport(16, 12),
            columns=80 + query_calls % 2,
            rows=24 + query_calls % 3,
            dpi=96.0,
        )

    def encode(frame: object, *, columns: int, rows: int) -> bytes:
        nonlocal encoded_frames
        del frame, columns, rows
        encoded_frames += 1
        return ESC + b"[38;2;" + b"p" * 5_000 + RESET_COLORS

    backend = WezTermBackend(
        pane_id=2,
        output=output,  # type: ignore[arg-type]
        query_geometry=query,
        frame_encoder=encode,  # type: ignore[arg-type]
    )
    font_data = b"synthetic-font"
    request = PreparedRun(
        text="猫",
        effect_id="pulse",
        orientation=Orientation.HORIZONTAL,
        font_data=font_data,
        font_fingerprint=hashlib.sha256(font_data).hexdigest(),
        fps=15,
        margin=0.08,
        seed=0,
        scene_id="rainy-night",
    )

    def rasterize(data: bytes, key: TypographyKey) -> TextMask:
        alpha = np.full((key.viewport.height_px, key.viewport.width_px), 180, dtype=np.uint8)
        return TextMask(key.viewport.width_px, key.viewport.height_px, alpha)

    backend.preflight()
    backend.enter()
    result = run_animation(
        request,
        backend=backend,
        clock=AdvancingClock(),
        rasterizer=rasterize,
        should_stop=lambda: encoded_frames == 1_000,
    )
    backend.restore()
    restored_bytes = output.total_bytes
    backend.restore()

    assert result.presented_frames == 1_000
    assert encoded_frames == 1_000
    assert query_calls > 60
    assert output.flushes == 1_002
    assert output.max_write == 5_011
    assert output.total_bytes < 8_000_000
    assert output.total_bytes == restored_bytes
    assert not hasattr(backend, "__dict__")
