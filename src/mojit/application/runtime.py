"""Resize-aware orchestration across pure rendering and runtime ports."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from numbers import Real

from mojit.application.mask_cache import TextMaskCache
from mojit.application.ports import AnimationBackend, MonotonicClock
from mojit.application.request import PreparedRun
from mojit.application.scheduler import FixedStepScheduler
from mojit.core.models import Frame, RenderContext, TextMask, Viewport
from mojit.core.typography import TypographyKey, rasterize_text_mask
from mojit.effects.api import Effect, EffectConfig
from mojit.effects.registry import get_effect

Rasterizer = Callable[[bytes, TypographyKey], TextMask]
StopPredicate = Callable[[], bool]

VIEWPORT_POLL_INTERVAL_SECONDS = 0.25


class RuntimeContractError(ValueError):
    """A runtime collaborator returned a value outside its structural contract."""


class InitialViewportUnavailableError(RuntimeError):
    """Animation cannot start without an initial pixel viewport."""


@dataclass(frozen=True, slots=True)
class AnimationResult:
    """Bounded counters returned after cooperative completion."""

    presented_frames: int
    last_frame_index: int | None
    skipped_frames: int
    viewport_changes: int


class RenderSession:
    """Compose one prepared request into deterministic frames."""

    __slots__ = ("_cache", "_config", "_rasterizer", "_renderer", "_request")

    def __init__(
        self,
        request: PreparedRun,
        *,
        rasterizer: Rasterizer = rasterize_text_mask,
    ) -> None:
        if not isinstance(request, PreparedRun):
            raise TypeError("request must be a PreparedRun")
        if not callable(rasterizer):
            raise TypeError("rasterizer must be callable")

        self._request = request
        self._renderer: Effect = get_effect(request.effect_id)
        self._config = EffectConfig(request.seed)
        self._rasterizer = rasterizer
        self._cache = TextMaskCache()

    def render(self, viewport: Viewport, frame_index: int) -> Frame:
        """Render one frame with cache identity and elapsed time derived explicitly."""
        if not isinstance(viewport, Viewport):
            raise TypeError("viewport must be a Viewport")

        key = TypographyKey(
            text=self._request.text,
            font_fingerprint=self._request.font_fingerprint,
            orientation=self._request.orientation,
            viewport=viewport,
            margin=self._request.margin,
        )
        mask = self._cache.get_or_create(
            key,
            lambda: self._rasterizer(self._request.font_data, key),
        )
        context = RenderContext(
            viewport=viewport,
            frame_index=frame_index,
            elapsed_seconds=frame_index / self._request.fps,
        )
        frame = self._renderer(mask, context, self._config)
        if not isinstance(frame, Frame):
            raise RuntimeContractError("effect must return a Frame")
        if (frame.width, frame.height) != (viewport.width_px, viewport.height_px):
            raise RuntimeContractError("effect frame dimensions must match the viewport")
        return frame


def _read_monotonic(clock: MonotonicClock, previous: float | None) -> float:
    value = clock.monotonic()
    if isinstance(value, bool) or not isinstance(value, Real):
        raise RuntimeContractError("clock.monotonic() must return a real number")
    timestamp = float(value)
    if not math.isfinite(timestamp):
        raise RuntimeContractError("clock.monotonic() must return a finite value")
    if previous is not None and timestamp < previous:
        raise RuntimeContractError("clock.monotonic() must not move backwards")
    return timestamp


def _validate_viewport(value: object, *, initial: bool) -> Viewport | None:
    if value is None:
        if initial:
            raise InitialViewportUnavailableError("initial viewport is unavailable")
        return None
    if not isinstance(value, Viewport):
        raise RuntimeContractError("backend.get_viewport() must return Viewport or None")
    return value


def _should_stop(predicate: StopPredicate | None) -> bool:
    if predicate is None:
        return False
    result = predicate()
    if not isinstance(result, bool):
        raise RuntimeContractError("should_stop() must return a boolean")
    return result


def _next_poll_deadline(started_at: float, now: float) -> float:
    completed_intervals = math.floor(max(0.0, now - started_at) / VIEWPORT_POLL_INTERVAL_SECONDS)
    deadline = started_at + (completed_intervals + 1) * VIEWPORT_POLL_INTERVAL_SECONDS
    if not math.isfinite(deadline):
        raise RuntimeContractError("viewport poll deadline must be finite")
    return deadline


def run_animation(
    request: PreparedRun,
    *,
    backend: AnimationBackend,
    clock: MonotonicClock,
    rasterizer: Rasterizer = rasterize_text_mask,
    should_stop: StopPredicate | None = None,
) -> AnimationResult:
    """Run synchronous animation until cooperative stop or a propagated failure."""
    if should_stop is not None and not callable(should_stop):
        raise TypeError("should_stop must be callable or None")

    session = RenderSession(request, rasterizer=rasterizer)
    viewport = _validate_viewport(backend.get_viewport(), initial=True)
    assert viewport is not None

    now = _read_monotonic(clock, None)
    scheduler = FixedStepScheduler(request.fps, now)
    next_frame_index = 0
    next_poll_at = _next_poll_deadline(now, now)
    presented_frames = 0
    last_frame_index: int | None = None
    skipped_frames = 0
    viewport_changes = 0

    while not _should_stop(should_stop):
        if now >= next_poll_at:
            candidate = _validate_viewport(backend.get_viewport(), initial=False)
            now = _read_monotonic(clock, now)
            if candidate is not None and candidate != viewport:
                viewport = candidate
                viewport_changes += 1
            next_poll_at = _next_poll_deadline(scheduler.started_at, now)

        due_index = scheduler.due_frame_index(now, next_frame_index)
        if due_index is not None:
            skipped_frames += due_index - next_frame_index
            frame = session.render(viewport, due_index)
            now = _read_monotonic(clock, now)
            backend.present(frame)
            now = _read_monotonic(clock, now)
            presented_frames += 1
            last_frame_index = due_index
            next_frame_index = due_index + 1
            continue

        wake_at = min(scheduler.deadline(next_frame_index), next_poll_at)
        delay = max(0.0, wake_at - now)
        if delay > 0.0:
            clock.sleep(delay)
        now = _read_monotonic(clock, now)

    return AnimationResult(
        presented_frames=presented_frames,
        last_frame_index=last_frame_index,
        skipped_frames=skipped_frames,
        viewport_changes=viewport_changes,
    )
