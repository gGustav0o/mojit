from __future__ import annotations

import hashlib

import numpy as np
import pytest

from mojit.application.request import PreparedRun
from mojit.application.runtime import RenderSession, run_animation
from mojit.config.models import DEFAULT_FPS
from mojit.core.models import Frame, Orientation, TextMask, Viewport
from mojit.core.typography import TypographyKey
from mojit.effects.registry import effect_names


def _request(effect_id: str, *, orientation: Orientation = Orientation.HORIZONTAL) -> PreparedRun:
    data = b"synthetic-font"
    return PreparedRun(
        text="電脳世界",
        effect_id=effect_id,
        orientation=orientation,
        font_data=data,
        font_fingerprint=hashlib.sha256(data).hexdigest(),
        fps=DEFAULT_FPS,
        margin=0.08,
        seed=42,
    )


def _synthetic_rasterizer(font_data: bytes, key: TypographyKey) -> TextMask:
    assert font_data == b"synthetic-font"
    alpha = np.zeros((key.viewport.height_px, key.viewport.width_px), dtype=np.uint8)
    alpha[
        key.viewport.height_px // 4 : 3 * key.viewport.height_px // 4,
        key.viewport.width_px // 4 : 3 * key.viewport.width_px // 4,
    ] = 220
    return TextMask(key.viewport.width_px, key.viewport.height_px, alpha)


@pytest.mark.parametrize("effect_id", effect_names())
@pytest.mark.parametrize("orientation", list(Orientation))
def test_prepared_run_renders_all_effects_without_system_dependencies(
    effect_id: str,
    orientation: Orientation,
) -> None:
    viewport = Viewport(31, 25)
    first_session = RenderSession(
        _request(effect_id, orientation=orientation),
        rasterizer=_synthetic_rasterizer,
    )
    second_session = RenderSession(
        _request(effect_id, orientation=orientation),
        rasterizer=_synthetic_rasterizer,
    )

    first = first_session.render(viewport, 13)
    repeated = first_session.render(viewport, 13)
    independent = second_session.render(viewport, 13)

    assert first == repeated == independent
    assert (first.width, first.height) == (31, 25)
    assert not first.rgba.flags.writeable


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class _ResizeBackend:
    def __init__(self) -> None:
        self.viewports = [Viewport(24, 18), None, Viewport(28, 20)]
        self.viewport_calls = 0
        self.frames: list[Frame] = []

    def get_viewport(self) -> Viewport | None:
        index = min(self.viewport_calls, len(self.viewports) - 1)
        self.viewport_calls += 1
        return self.viewports[index]

    def present(self, frame: Frame) -> None:
        self.frames.append(frame)


def test_runtime_composes_cache_resize_effect_and_presentation() -> None:
    backend = _ResizeBackend()
    rasterized: list[Viewport] = []

    def rasterize(font_data: bytes, key: TypographyKey) -> TextMask:
        rasterized.append(key.viewport)
        return _synthetic_rasterizer(font_data, key)

    result = run_animation(
        _request("glitch"),
        backend=backend,
        clock=_Clock(),
        rasterizer=rasterize,
        should_stop=lambda: len(backend.frames) == 17,
    )

    assert result.presented_frames == 17
    assert result.last_frame_index == 16
    assert result.skipped_frames == 0
    assert result.viewport_changes == 1
    assert rasterized == [Viewport(24, 18), Viewport(28, 20)]
    assert [(frame.width, frame.height) for frame in backend.frames[:4]] == [(24, 18)] * 4
    assert [(frame.width, frame.height) for frame in backend.frames[4:]] == [(28, 20)] * 13
