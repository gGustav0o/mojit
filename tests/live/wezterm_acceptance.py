from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path

import pytest

from mojit.adapters.clock import SystemMonotonicClock
from mojit.adapters.font_resource import load_font_resource
from mojit.adapters.wezterm.backend import WezTermBackend
from mojit.adapters.wezterm.viewport import parse_pane_id, query_pane_geometry
from mojit.application.request import PreparedRun
from mojit.application.runtime import AnimationResult, run_animation
from mojit.cli import create_rasterizer
from mojit.config.models import DEFAULT_FPS
from mojit.core.models import Frame, Orientation, Viewport
from mojit.core.timing import MAX_FPS
from mojit.core.typography import require_shaping_capability
from mojit.scenes.presets import scene_names

pytestmark = pytest.mark.wezterm_live

FONT_PATH = "C:/Windows/Fonts/YuGothB.ttc"


class LiveOutput:
    __slots__ = ("_stream", "bytes_written", "flushes", "max_write")

    def __init__(self) -> None:
        stream = getattr(sys.stdout, "buffer", None)
        if stream is None or not sys.stdout.isatty():
            raise AssertionError("live acceptance requires interactive binary stdout")
        self._stream = stream
        self.bytes_written = 0
        self.flushes = 0
        self.max_write = 0

    def write(self, value: bytes | memoryview) -> int:
        written = self._stream.write(value)
        self.bytes_written += written
        self.max_write = max(self.max_write, written)
        return written

    def flush(self) -> None:
        self._stream.flush()
        self.flushes += 1


@dataclass(slots=True)
class PresentationMetrics:
    frames: int = 0
    latency_sum_seconds: float = 0.0
    latency_max_seconds: float = 0.0
    viewports: list[tuple[int, int]] = field(default_factory=list)


class MeasuredBackend:
    __slots__ = ("_backend", "_fail_after", "metrics")

    def __init__(self, backend: WezTermBackend, *, fail_after: int | None = None) -> None:
        self._backend = backend
        self._fail_after = fail_after
        self.metrics = PresentationMetrics()

    def get_viewport(self) -> Viewport | None:
        viewport = self._backend.get_viewport()
        if viewport is not None:
            dimensions = (viewport.width_px, viewport.height_px)
            if not self.metrics.viewports or self.metrics.viewports[-1] != dimensions:
                self.metrics.viewports.append(dimensions)
        return viewport

    def present(self, frame: Frame) -> None:
        if self._fail_after is not None and self.metrics.frames == self._fail_after:
            raise RuntimeError("injected live runtime failure")
        started = time.perf_counter()
        self._backend.present(frame)
        latency = time.perf_counter() - started
        self.metrics.frames += 1
        self.metrics.latency_sum_seconds += latency
        self.metrics.latency_max_seconds = max(self.metrics.latency_max_seconds, latency)


def _request(
    orientation: Orientation,
    *,
    fps: int = DEFAULT_FPS,
    scene_id: str | None = None,
) -> PreparedRun:
    font = load_font_resource(FONT_PATH)
    require_shaping_capability()
    return PreparedRun(
        text="電脳世界",
        effect_id="neon",
        orientation=orientation,
        font_data=font.data,
        font_fingerprint=font.fingerprint,
        fps=fps,
        margin=0.08,
        seed=42,
        scene_id=scene_id,
    )


def _backend() -> tuple[WezTermBackend, LiveOutput]:
    output = LiveOutput()
    pane_id = parse_pane_id(os.environ)
    backend = WezTermBackend(
        pane_id=pane_id,
        output=output,  # type: ignore[arg-type]
        query_geometry=partial(query_pane_geometry),
    )
    return backend, output


def _visible_cursor() -> bool:
    pane_id = parse_pane_id(os.environ)
    result = subprocess.run(
        ("wezterm", "cli", "list", "--format", "json"),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=True,
        timeout=2.0,
    )
    panes = json.loads(result.stdout.decode("utf-8", errors="strict"))
    matches = [pane for pane in panes if pane.get("pane_id") == pane_id]
    return len(matches) == 1 and matches[0].get("cursor_visibility") == "Visible"


def _run_bounded(
    orientation: Orientation,
    *,
    frames: int,
    fps: int = DEFAULT_FPS,
    fail_after: int | None = None,
    should_stop: Callable[[], bool] | None = None,
    scene_id: str | None = None,
) -> tuple[AnimationResult | None, PresentationMetrics, LiveOutput]:
    request = _request(orientation, fps=fps, scene_id=scene_id)
    backend, output = _backend()
    measured = MeasuredBackend(backend, fail_after=fail_after)
    result: AnimationResult | None = None
    backend.preflight()
    try:
        backend.enter()
        result = run_animation(
            request,
            backend=measured,
            clock=SystemMonotonicClock(),
            rasterizer=create_rasterizer(request),
            should_stop=should_stop or (lambda: measured.metrics.frames == frames),
        )
    finally:
        backend.restore()
        backend.restore()
    return result, measured.metrics, output


@pytest.mark.parametrize("orientation", list(Orientation))
@pytest.mark.parametrize("fps", [DEFAULT_FPS, MAX_FPS])
def test_live_cjk_orientation_and_restore(orientation: Orientation, fps: int) -> None:
    result, metrics, output = _run_bounded(orientation, frames=12, fps=fps)
    assert result is not None
    assert result.presented_frames == 12
    assert result.last_frame_index is not None
    assert result.last_frame_index + 1 == result.presented_frames + result.skipped_frames
    assert metrics.frames == 12
    assert output.bytes_written > 0
    assert _visible_cursor()


def test_live_runtime_failure_and_repeated_restore() -> None:
    with pytest.raises(RuntimeError, match="injected live runtime failure"):
        _run_bounded(
            Orientation.HORIZONTAL,
            frames=20,
            fail_after=3,
            scene_id="rainy-night",
        )
    assert _visible_cursor()


@pytest.mark.parametrize("scene_id", scene_names())
def test_live_ambient_scene_and_restore(scene_id: str) -> None:
    result, metrics, output = _run_bounded(
        Orientation.HORIZONTAL,
        frames=12,
        scene_id=scene_id,
    )
    assert result is not None
    assert result.presented_frames == 12
    assert metrics.frames == 12
    assert output.bytes_written > 0
    assert _visible_cursor()


def _wezterm_working_set() -> int:
    command = "(Get-Process wezterm-gui | Measure-Object -Property WorkingSet64 -Sum).Sum"
    result = subprocess.run(
        ("powershell.exe", "-NoProfile", "-Command", command),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=True,
        timeout=5.0,
    )
    return int(result.stdout.decode("ascii", errors="strict").strip())


def _adjust_pane(direction: str) -> None:
    subprocess.run(
        (
            "wezterm",
            "cli",
            "adjust-pane-size",
            "--pane-id",
            os.environ["WEZTERM_PANE"],
            "--amount",
            "4",
            direction,
        ),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=True,
        timeout=2.0,
    )


def test_live_structured_soak_with_resize_metrics() -> None:
    duration = float(os.environ.get("MOJIT_LIVE_SOAK_SECONDS", "300"))
    assert duration >= 1.0
    working_set_before = _wezterm_working_set()
    started = time.perf_counter()
    next_resize_at = started + min(1.0, duration / 4.0)
    resize_attempts = 0
    resize_directions = ("Left", "Right", "Up", "Down")

    def stop_or_resize() -> bool:
        nonlocal next_resize_at, resize_attempts
        now = time.perf_counter()
        if now >= next_resize_at and resize_attempts < len(resize_directions):
            _adjust_pane(resize_directions[resize_attempts])
            resize_attempts += 1
            next_resize_at = started + duration * (resize_attempts + 1) / 5.0
        return now - started >= duration

    result, metrics, output = _run_bounded(
        Orientation.HORIZONTAL,
        frames=0,
        scene_id="rainy-night",
        should_stop=stop_or_resize,
    )
    elapsed = time.perf_counter() - started
    working_set_after = _wezterm_working_set()

    assert result is not None
    assert result.presented_frames == metrics.frames
    assert result.presented_frames > 0
    assert resize_attempts == 4
    assert result.viewport_changes >= 4
    assert len(metrics.viewports) == result.viewport_changes + 1
    assert len({width for width, _ in metrics.viewports}) >= 2
    assert len({height for _, height in metrics.viewports}) >= 2
    assert _visible_cursor()
    total_frame_opportunities = result.presented_frames + result.skipped_frames
    metrics_json = json.dumps(
        {
            "target_fps": DEFAULT_FPS,
            "duration_seconds": elapsed,
            "frames": metrics.frames,
            "achieved_fps": metrics.frames / elapsed,
            "skipped_frames": result.skipped_frames,
            "skipped_frame_ratio": (
                result.skipped_frames / total_frame_opportunities
                if total_frame_opportunities
                else 0.0
            ),
            "average_present_ms": (metrics.latency_sum_seconds / metrics.frames * 1_000.0),
            "maximum_present_ms": metrics.latency_max_seconds * 1_000.0,
            "terminal_bytes": output.bytes_written,
            "maximum_write_bytes": output.max_write,
            "viewport_changes": result.viewport_changes,
            "viewports": metrics.viewports,
            "resize_attempts": resize_attempts,
            "resize_directions": resize_directions,
            "wezterm_working_set_before": working_set_before,
            "wezterm_working_set_after": working_set_after,
            "wezterm_working_set_delta": working_set_after - working_set_before,
        },
        sort_keys=True,
    )
    print("MOJIT_LIVE_METRICS=" + metrics_json)
    metrics_path = os.environ.get("MOJIT_LIVE_METRICS_PATH")
    if metrics_path:
        Path(metrics_path).write_text(metrics_json, encoding="utf-8")
