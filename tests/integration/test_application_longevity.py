from __future__ import annotations

import hashlib

import numpy as np

from mojit.application.request import PreparedRun
from mojit.application.runtime import run_animation
from mojit.core.models import Frame, Orientation, TextMask, Viewport
from mojit.core.typography import TypographyKey


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class _BoundedBackend:
    def __init__(self) -> None:
        self.viewport_calls = 0
        self.presented_frames = 0
        self.last_frame: Frame | None = None

    def get_viewport(self) -> Viewport:
        viewport = Viewport(4, 4) if self.viewport_calls % 2 == 0 else Viewport(5, 4)
        self.viewport_calls += 1
        return viewport

    def present(self, frame: Frame) -> None:
        self.presented_frames += 1
        self.last_frame = frame


def test_long_running_state_remains_bounded_across_frames_and_resizes() -> None:
    font_data = b"synthetic-font"
    request = PreparedRun(
        text="猫",
        effect_id="pulse",
        orientation=Orientation.HORIZONTAL,
        font_data=font_data,
        font_fingerprint=hashlib.sha256(font_data).hexdigest(),
        fps=60,
        margin=0.08,
        seed=0,
    )
    backend = _BoundedBackend()
    rasterized: list[Viewport] = []

    def rasterize(data: bytes, key: TypographyKey) -> TextMask:
        assert data == font_data
        rasterized.append(key.viewport)
        alpha = np.full(
            (key.viewport.height_px, key.viewport.width_px),
            180,
            dtype=np.uint8,
        )
        return TextMask(key.viewport.width_px, key.viewport.height_px, alpha)

    result = run_animation(
        request,
        backend=backend,
        clock=_Clock(),
        rasterizer=rasterize,
        should_stop=lambda: backend.presented_frames == 1_000,
    )

    assert result.presented_frames == 1_000
    assert result.last_frame_index == 999
    assert result.skipped_frames == 0
    assert result.viewport_changes == backend.viewport_calls - 1
    assert len(rasterized) == backend.viewport_calls
    assert backend.last_frame is not None
    assert len(vars(backend)) == 3
