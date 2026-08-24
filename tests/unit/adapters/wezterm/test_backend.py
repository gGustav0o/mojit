from __future__ import annotations

import io

import numpy as np
import pytest

from mojit.adapters.wezterm.backend import WezTermBackend
from mojit.adapters.wezterm.errors import (
    BackendStateError,
    CellEncodingError,
    ViewportQueryError,
    WezTermPreflightError,
)
from mojit.adapters.wezterm.viewport import CommandResult, PaneGeometry
from mojit.core.models import Frame, Viewport

CELL_PAYLOAD = b"\x1b[38;2;0;0;0m\x1b[48;2;0;0;0m" + "▀".encode() + b"\x1b[0m"


def _geometry(
    width: int = 8,
    height: int = 6,
    *,
    pane_id: int = 2,
    columns: int = 80,
    rows: int = 24,
) -> PaneGeometry:
    return PaneGeometry(pane_id, Viewport(width, height), columns, rows, 96.0)


def _frame(width: int = 8, height: int = 6) -> Frame:
    return Frame(width, height, np.zeros((height, width, 4), dtype=np.uint8))


def _backend(
    query: object,
    *,
    output: io.BytesIO | None = None,
    encoder: object | None = None,
) -> WezTermBackend:
    kwargs: dict[str, object] = {
        "pane_id": 2,
        "output": io.BytesIO() if output is None else output,
        "query_geometry": query,
        "presentation_pause": 0.0,
    }
    if encoder is not None:
        kwargs["frame_encoder"] = encoder
    return WezTermBackend(**kwargs)  # type: ignore[arg-type]


def test_preflight_caches_initial_geometry_and_is_idempotent() -> None:
    calls: list[int] = []

    def query(pane_id: int) -> PaneGeometry:
        calls.append(pane_id)
        return _geometry()

    backend = _backend(query)
    backend.preflight()
    backend.preflight()

    assert calls == [2]
    assert backend.get_viewport() == Viewport(8, 6)
    assert calls == [2]
    assert backend.get_viewport() == Viewport(8, 6)
    assert calls == [2, 2]


def test_transient_poll_failure_returns_none_and_retains_geometry() -> None:
    results: list[PaneGeometry | Exception] = [_geometry(), ViewportQueryError("busy")]

    def query(pane_id: int) -> PaneGeometry:
        result = results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    output = io.BytesIO()
    backend = _backend(
        query,
        output=output,
        encoder=lambda frame, *, columns, rows: CELL_PAYLOAD,
    )
    backend.preflight()
    backend.enter()
    assert backend.get_viewport() == Viewport(8, 6)
    assert backend.get_viewport() is None
    backend.present(_frame())
    backend.restore()
    assert CELL_PAYLOAD in output.getvalue()


def test_cell_only_geometry_change_is_used_for_next_presentation() -> None:
    results = [_geometry(), _geometry(columns=100, rows=30)]
    output = io.BytesIO()
    observed_geometry: list[tuple[int, int]] = []

    def encode(frame: Frame, *, columns: int, rows: int) -> bytes:
        del frame
        observed_geometry.append((columns, rows))
        return CELL_PAYLOAD

    backend = _backend(lambda pane_id: results.pop(0), output=output, encoder=encode)

    backend.preflight()
    backend.enter()
    assert backend.get_viewport() == Viewport(8, 6)
    assert backend.get_viewport() == Viewport(8, 6)
    backend.present(_frame())
    backend.restore()

    assert observed_geometry == [(100, 30)]


def test_preflight_maps_expected_query_failure_before_terminal_entry() -> None:
    output = io.BytesIO()
    backend = _backend(
        lambda pane_id: (_ for _ in ()).throw(ViewportQueryError("socket")),
        output=output,
    )

    with pytest.raises(WezTermPreflightError, match="socket"):
        backend.preflight()

    backend.restore()
    assert output.getvalue() == b""


@pytest.mark.parametrize("geometry", [object(), _geometry(pane_id=3)])
def test_preflight_rejects_wrong_geometry_contract(geometry: object) -> None:
    backend = _backend(lambda pane_id: geometry)
    with pytest.raises(WezTermPreflightError, match="wrong pane"):
        backend.preflight()


def test_runtime_rejects_wrong_geometry_contract() -> None:
    results = [_geometry(), _geometry(pane_id=3)]
    backend = _backend(lambda pane_id: results.pop(0))
    backend.preflight()
    backend.get_viewport()
    with pytest.raises(BackendStateError, match="wrong pane"):
        backend.get_viewport()


def test_backend_enforces_lifecycle_and_frame_dimensions() -> None:
    backend = _backend(
        lambda pane_id: _geometry(),
        encoder=lambda frame, *, columns, rows: CELL_PAYLOAD,
    )

    with pytest.raises(BackendStateError, match="preflighted"):
        backend.enter()
    with pytest.raises(BackendStateError, match="preflighted"):
        backend.get_viewport()
    with pytest.raises(BackendStateError, match="active"):
        backend.present(_frame())

    backend.preflight()
    backend.enter()
    with pytest.raises(BackendStateError, match="dimensions"):
        backend.present(_frame(7, 6))
    with pytest.raises(TypeError, match="Frame"):
        backend.present(object())  # type: ignore[arg-type]
    with pytest.raises(BackendStateError, match="preflight"):
        backend.preflight()
    backend.restore()


def test_encoder_failure_occurs_before_terminal_presentation_mutation() -> None:
    output = io.BytesIO()

    def fail(frame: Frame, *, columns: int, rows: int) -> bytes:
        del frame, columns, rows
        raise CellEncodingError("encode")

    backend = _backend(lambda pane_id: _geometry(), output=output, encoder=fail)
    backend.preflight()
    backend.enter()
    entered = output.getvalue()

    with pytest.raises(CellEncodingError, match="encode"):
        backend.present(_frame())

    assert output.getvalue() == entered
    backend.restore()


def test_restore_is_idempotent_and_does_not_close_output() -> None:
    output = io.BytesIO()
    backend = _backend(lambda pane_id: _geometry(), output=output)
    backend.preflight()
    backend.enter()
    backend.restore()
    restored = output.getvalue()
    backend.restore()
    assert output.getvalue() == restored
    assert output.closed is False


def test_presentation_pause_runs_after_the_frame_is_flushed() -> None:
    output = io.BytesIO()
    observations: list[tuple[float, bytes]] = []
    backend = WezTermBackend(
        pane_id=2,
        output=output,
        query_geometry=lambda pane_id: _geometry(),
        frame_encoder=lambda frame, *, columns, rows: CELL_PAYLOAD,
        presentation_pause=0.1,
        sleeper=lambda delay: observations.append((delay, output.getvalue())),
    )

    backend.preflight()
    backend.enter()
    backend.present(_frame())
    backend.restore()

    assert len(observations) == 1
    assert observations[0][0] == 0.1
    assert CELL_PAYLOAD in observations[0][1]


def test_from_environment_validates_tty_and_uses_exact_pane() -> None:
    document = (
        b'[{"pane_id":7,"size":{"rows":24,"cols":80,"pixel_width":8,"pixel_height":6,"dpi":96}}]'
    )
    calls: list[tuple[tuple[str, ...], float]] = []

    def runner(command: tuple[str, ...], timeout: float) -> CommandResult:
        calls.append((command, timeout))
        return CommandResult(0, document, b"")

    backend = WezTermBackend.from_environment(
        {"WEZTERM_PANE": "7"},
        output=io.BytesIO(),
        output_is_terminal=True,
        runner=runner,
    )
    backend.preflight()

    assert len(calls) == 1


def test_from_environment_rejects_non_terminal_before_pane_query() -> None:
    called = False

    def runner(command: tuple[str, ...], timeout: float) -> CommandResult:
        nonlocal called
        called = True
        raise AssertionError

    with pytest.raises(WezTermPreflightError, match="interactive"):
        WezTermBackend.from_environment(
            {"WEZTERM_PANE": "2"},
            output=io.BytesIO(),
            output_is_terminal=False,
            runner=runner,
        )
    assert called is False


@pytest.mark.parametrize(
    "kwargs",
    [
        {"pane_id": True},
        {"pane_id": -1},
        {"query_geometry": object()},
        {"frame_encoder": object()},
        {"presentation_pause": -0.1},
        {"presentation_pause": float("nan")},
        {"sleeper": object()},
    ],
)
def test_constructor_rejects_invalid_collaborators(kwargs: dict[str, object]) -> None:
    values: dict[str, object] = {
        "pane_id": 2,
        "output": io.BytesIO(),
        "query_geometry": lambda pane_id: _geometry(),
        "presentation_pause": 0.0,
    }
    values.update(kwargs)
    with pytest.raises(TypeError):
        WezTermBackend(**values)  # type: ignore[arg-type]
