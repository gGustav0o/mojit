from __future__ import annotations

import hashlib
import math

import numpy as np
import pytest

import mojit.application.runtime as runtime_module
from mojit.application.request import PreparedRun
from mojit.application.runtime import (
    AnimationResult,
    InitialViewportUnavailableError,
    RenderSession,
    RuntimeContractError,
    run_animation,
)
from mojit.core.models import Frame, Orientation, RenderContext, TextMask, Viewport
from mojit.core.typography import TypographyKey
from mojit.effects.api import EffectConfig
from mojit.effects.registry import UnknownEffectError


def _request(**changes: object) -> PreparedRun:
    font_data = b"font"
    values: dict[str, object] = {
        "text": "猫",
        "effect_id": "neon",
        "orientation": Orientation.HORIZONTAL,
        "font_data": font_data,
        "font_fingerprint": hashlib.sha256(font_data).hexdigest(),
        "fps": 4,
        "margin": 0.08,
        "seed": 17,
        "debug": False,
    }
    values.update(changes)
    return PreparedRun(**values)  # type: ignore[arg-type]


def _mask_for(key: TypographyKey, value: int = 255) -> TextMask:
    return TextMask(
        key.viewport.width_px,
        key.viewport.height_px,
        np.full(
            (key.viewport.height_px, key.viewport.width_px),
            value,
            dtype=np.uint8,
        ),
    )


def _frame_for(viewport: Viewport, value: int = 0) -> Frame:
    return Frame(
        viewport.width_px,
        viewport.height_px,
        np.full(
            (viewport.height_px, viewport.width_px, 4),
            value,
            dtype=np.uint8,
        ),
    )


def _install_recording_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> list[tuple[TextMask, RenderContext, EffectConfig]]:
    calls: list[tuple[TextMask, RenderContext, EffectConfig]] = []

    def render(mask: TextMask, context: RenderContext, config: EffectConfig) -> Frame:
        calls.append((mask, context, config))
        return _frame_for(context.viewport, value=context.frame_index % 256)

    monkeypatch.setattr(runtime_module, "get_effect", lambda effect_id: render)
    return calls


class FakeClock:
    def __init__(self, now: float = 0.0) -> None:
        self.now = now
        self.sleeps: list[float] = []
        self.reads = 0

    def monotonic(self) -> float:
        self.reads += 1
        return self.now

    def sleep(self, seconds: float) -> None:
        assert math.isfinite(seconds)
        assert seconds >= 0.0
        self.sleeps.append(seconds)
        self.now += seconds

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeBackend:
    def __init__(
        self,
        responses: list[object],
        *,
        clock: FakeClock | None = None,
        poll_cost: float = 0.0,
        present_cost: float = 0.0,
    ) -> None:
        self.responses = responses
        self.clock = clock
        self.poll_cost = poll_cost
        self.present_cost = present_cost
        self.viewport_calls = 0
        self.frames: list[Frame] = []

    def get_viewport(self) -> Viewport | None:
        index = min(self.viewport_calls, len(self.responses) - 1)
        response = self.responses[index]
        self.viewport_calls += 1
        if self.viewport_calls > 1 and self.clock is not None:
            self.clock.advance(self.poll_cost)
        if isinstance(response, BaseException):
            raise response
        return response  # type: ignore[return-value]

    def present(self, frame: Frame) -> None:
        self.frames.append(frame)
        if self.clock is not None:
            self.clock.advance(self.present_cost)


def test_render_session_reuses_mask_and_builds_exact_deterministic_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    effect_calls = _install_recording_effect(monkeypatch)
    raster_calls: list[tuple[bytes, TypographyKey]] = []

    def rasterize(font_data: bytes, key: TypographyKey) -> TextMask:
        raster_calls.append((font_data, key))
        return _mask_for(key)

    session = RenderSession(_request(fps=10), rasterizer=rasterize)
    viewport = Viewport(8, 6)
    first = session.render(viewport, 0)
    second = session.render(viewport, 7)

    assert (first.width, first.height) == (8, 6)
    assert (second.width, second.height) == (8, 6)
    assert len(raster_calls) == 1
    assert raster_calls[0][0] == b"font"
    key = raster_calls[0][1]
    assert key.text == "猫"
    assert key.orientation is Orientation.HORIZONTAL
    assert key.viewport == viewport
    assert key.margin == 0.08
    assert [call[1].frame_index for call in effect_calls] == [0, 7]
    assert [call[1].elapsed_seconds for call in effect_calls] == [0.0, 7 / 10]
    assert effect_calls[0][2] is effect_calls[1][2]
    assert effect_calls[0][2].seed == 17


def test_render_session_resize_replaces_cache_and_returning_to_old_size_misses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_recording_effect(monkeypatch)
    rasterized: list[Viewport] = []

    def rasterize(font_data: bytes, key: TypographyKey) -> TextMask:
        del font_data
        rasterized.append(key.viewport)
        return _mask_for(key)

    session = RenderSession(_request(), rasterizer=rasterize)
    first = Viewport(8, 6)
    second = Viewport(10, 7)
    session.render(first, 0)
    session.render(second, 1)
    session.render(second, 2)
    session.render(first, 3)

    assert rasterized == [first, second, first]


def test_render_session_rejects_invalid_construction_and_viewport() -> None:
    with pytest.raises(TypeError, match="PreparedRun"):
        RenderSession(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="rasterizer"):
        RenderSession(_request(), rasterizer=object())  # type: ignore[arg-type]
    with pytest.raises(UnknownEffectError):
        RenderSession(_request(effect_id="unknown"))

    with pytest.raises(TypeError, match="viewport"):
        RenderSession(_request()).render(object(), 0)  # type: ignore[arg-type]


@pytest.mark.parametrize("wrong_result", [object(), _frame_for(Viewport(1, 1))])
def test_render_session_rejects_invalid_effect_output(
    monkeypatch: pytest.MonkeyPatch,
    wrong_result: object,
) -> None:
    monkeypatch.setattr(runtime_module, "get_effect", lambda effect_id: lambda *args: wrong_result)
    session = RenderSession(_request(), rasterizer=lambda data, key: _mask_for(key))
    with pytest.raises(RuntimeContractError, match="effect"):
        session.render(Viewport(8, 6), 0)


def test_run_presents_frame_zero_immediately_without_sleep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    effect_calls = _install_recording_effect(monkeypatch)
    clock = FakeClock(now=11.0)
    backend = FakeBackend([Viewport(8, 6)])

    result = run_animation(
        _request(),
        backend=backend,
        clock=clock,
        rasterizer=lambda data, key: _mask_for(key),
        should_stop=lambda: len(backend.frames) == 1,
    )

    assert result == AnimationResult(1, 0, 0, 0)
    assert effect_calls[0][1].elapsed_seconds == 0.0
    assert clock.sleeps == []


def test_run_can_stop_cooperatively_before_first_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_recording_effect(monkeypatch)
    backend = FakeBackend([Viewport(8, 6)])
    result = run_animation(
        _request(),
        backend=backend,
        clock=FakeClock(),
        rasterizer=lambda data, key: _mask_for(key),
        should_stop=lambda: True,
    )
    assert result == AnimationResult(0, None, 0, 0)
    assert backend.viewport_calls == 1
    assert backend.frames == []


def test_viewport_polling_is_independent_from_one_fps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_recording_effect(monkeypatch)
    clock = FakeClock()
    backend = FakeBackend([Viewport(8, 6)])

    result = run_animation(
        _request(fps=1),
        backend=backend,
        clock=clock,
        rasterizer=lambda data, key: _mask_for(key),
        should_stop=lambda: len(backend.frames) == 2,
    )

    assert result.last_frame_index == 1
    assert backend.viewport_calls == 5
    assert clock.sleeps == [0.25, 0.25, 0.25, 0.25]


def test_transient_poll_failure_retains_viewport_and_resize_precedes_due_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    effect_calls = _install_recording_effect(monkeypatch)
    first = Viewport(8, 6)
    second = Viewport(10, 7)
    clock = FakeClock()
    backend = FakeBackend([first, None, second])
    rasterized: list[Viewport] = []

    def rasterize(data: bytes, key: TypographyKey) -> TextMask:
        del data
        rasterized.append(key.viewport)
        return _mask_for(key)

    result = run_animation(
        _request(fps=4),
        backend=backend,
        clock=clock,
        rasterizer=rasterize,
        should_stop=lambda: len(backend.frames) == 3,
    )

    assert [call[1].viewport for call in effect_calls] == [first, first, second]
    assert rasterized == [first, second]
    assert result == AnimationResult(3, 2, 0, 1)


def test_late_rendering_skips_indices_without_catch_up_burst(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    effect_calls = _install_recording_effect(monkeypatch)
    clock = FakeClock()
    backend = FakeBackend(
        [Viewport(8, 6)],
        clock=clock,
        present_cost=0.35,
    )

    result = run_animation(
        _request(fps=10),
        backend=backend,
        clock=clock,
        rasterizer=lambda data, key: _mask_for(key),
        should_stop=lambda: len(backend.frames) == 2,
    )

    assert [call[1].frame_index for call in effect_calls] == [0, 3]
    assert result == AnimationResult(2, 3, 2, 0)


def test_late_poll_advances_directly_without_replaying_missed_polls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_recording_effect(monkeypatch)
    clock = FakeClock()
    backend = FakeBackend(
        [Viewport(8, 6)],
        clock=clock,
        poll_cost=1.0,
    )

    result = run_animation(
        _request(fps=1),
        backend=backend,
        clock=clock,
        rasterizer=lambda data, key: _mask_for(key),
        should_stop=lambda: len(backend.frames) == 2,
    )

    assert backend.viewport_calls == 2
    assert result.last_frame_index == 1


@pytest.mark.parametrize("initial", [None, object()])
def test_run_requires_valid_initial_viewport_before_clock_or_presentation(
    monkeypatch: pytest.MonkeyPatch,
    initial: object,
) -> None:
    _install_recording_effect(monkeypatch)
    clock = FakeClock()
    backend = FakeBackend([initial])
    expected = InitialViewportUnavailableError if initial is None else RuntimeContractError
    with pytest.raises(expected):
        run_animation(
            _request(),
            backend=backend,
            clock=clock,
            rasterizer=lambda data, key: _mask_for(key),
        )
    assert clock.reads == 0
    assert backend.frames == []


@pytest.mark.parametrize("value", [True, "zero", float("nan"), float("inf")])
def test_run_rejects_invalid_clock_reading(
    monkeypatch: pytest.MonkeyPatch,
    value: object,
) -> None:
    _install_recording_effect(monkeypatch)

    class InvalidClock:
        def monotonic(self) -> float:
            return value  # type: ignore[return-value]

        def sleep(self, seconds: float) -> None:
            del seconds

    with pytest.raises(RuntimeContractError, match="clock.monotonic"):
        run_animation(
            _request(),
            backend=FakeBackend([Viewport(8, 6)]),
            clock=InvalidClock(),
            rasterizer=lambda data, key: _mask_for(key),
        )


def test_run_rejects_clock_moving_backwards(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_recording_effect(monkeypatch)

    class BackwardsClock:
        values = iter([1.0, 0.5])

        def monotonic(self) -> float:
            return next(self.values)

        def sleep(self, seconds: float) -> None:
            del seconds

    with pytest.raises(RuntimeContractError, match="backwards"):
        run_animation(
            _request(),
            backend=FakeBackend([Viewport(8, 6)]),
            clock=BackwardsClock(),
            rasterizer=lambda data, key: _mask_for(key),
        )


def test_run_rejects_invalid_stop_collaborator(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_recording_effect(monkeypatch)
    arguments = {
        "request": _request(),
        "backend": FakeBackend([Viewport(8, 6)]),
        "clock": FakeClock(),
        "rasterizer": lambda data, key: _mask_for(key),
    }
    with pytest.raises(TypeError, match="should_stop"):
        run_animation(**arguments, should_stop=object())  # type: ignore[arg-type]
    with pytest.raises(RuntimeContractError, match="boolean"):
        run_animation(**arguments, should_stop=lambda: 1)  # type: ignore[arg-type]


@pytest.mark.parametrize("failure", [RuntimeError("present failed"), KeyboardInterrupt()])
def test_presentation_failures_propagate_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    failure: BaseException,
) -> None:
    _install_recording_effect(monkeypatch)

    class FailingBackend(FakeBackend):
        def present(self, frame: Frame) -> None:
            del frame
            raise failure

    with pytest.raises(type(failure), match=str(failure) or None):
        run_animation(
            _request(),
            backend=FailingBackend([Viewport(8, 6)]),
            clock=FakeClock(),
            rasterizer=lambda data, key: _mask_for(key),
        )


def test_runtime_poll_failure_propagates_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_recording_effect(monkeypatch)
    failure = RuntimeError("viewport failed")
    backend = FakeBackend([Viewport(8, 6), failure])
    with pytest.raises(RuntimeError, match="viewport failed"):
        run_animation(
            _request(fps=1),
            backend=backend,
            clock=FakeClock(),
            rasterizer=lambda data, key: _mask_for(key),
        )
    assert backend.viewport_calls == 2


def test_runtime_rejects_invalid_runtime_viewport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_recording_effect(monkeypatch)
    backend = FakeBackend([Viewport(8, 6), object()])
    with pytest.raises(RuntimeContractError, match="Viewport or None"):
        run_animation(
            _request(fps=1),
            backend=backend,
            clock=FakeClock(),
            rasterizer=lambda data, key: _mask_for(key),
        )
