"""Concrete production composition for viewport, cells, and terminal state."""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Mapping
from functools import partial
from numbers import Real
from typing import BinaryIO, Protocol

from mojit.adapters.wezterm.cell_encoder import CellEncoder
from mojit.adapters.wezterm.errors import (
    BackendStateError,
    ViewportQueryError,
    WezTermPreflightError,
)
from mojit.adapters.wezterm.terminal_state import TerminalSession
from mojit.adapters.wezterm.viewport import (
    PaneGeometry,
    Runner,
    parse_pane_id,
    query_pane_geometry,
    run_wezterm_cli,
)
from mojit.core.models import Frame, Viewport

GeometryQuery = Callable[[int], PaneGeometry]
Sleeper = Callable[[float], None]


class FrameEncoder(Protocol):
    """Encode a pixel frame for one exact terminal cell geometry."""

    def __call__(self, frame: Frame, *, columns: int, rows: int) -> bytes: ...


class WezTermBackend:
    """Implement the Phase 4 backend port without importing application."""

    __slots__ = (
        "_frame_encoder",
        "_geometry",
        "_initial_pending",
        "_pane_id",
        "_preflighted",
        "_presentation_pause",
        "_query_geometry",
        "_sleep",
        "_terminal",
    )

    def __init__(
        self,
        *,
        pane_id: int,
        output: BinaryIO,
        query_geometry: GeometryQuery,
        frame_encoder: FrameEncoder | None = None,
        presentation_pause: float = 0.1,
        sleeper: Sleeper = time.sleep,
    ) -> None:
        if isinstance(pane_id, bool) or not isinstance(pane_id, int) or pane_id < 0:
            raise TypeError("pane_id must be a non-negative integer")
        if not callable(query_geometry):
            raise TypeError("query_geometry must be callable")
        if frame_encoder is not None and not callable(frame_encoder):
            raise TypeError("frame_encoder must be callable")
        if (
            isinstance(presentation_pause, bool)
            or not isinstance(presentation_pause, Real)
            or not math.isfinite(float(presentation_pause))
            or presentation_pause < 0.0
        ):
            raise TypeError("presentation_pause must be a finite non-negative real")
        if not callable(sleeper):
            raise TypeError("sleeper must be callable")
        self._pane_id = pane_id
        self._query_geometry = query_geometry
        self._frame_encoder = CellEncoder() if frame_encoder is None else frame_encoder
        self._presentation_pause = float(presentation_pause)
        self._sleep = sleeper
        self._terminal = TerminalSession(output)
        self._geometry: PaneGeometry | None = None
        self._preflighted = False
        self._initial_pending = False

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str],
        *,
        output: BinaryIO,
        output_is_terminal: bool,
        runner: Runner = run_wezterm_cli,
    ) -> WezTermBackend:
        """Build one process backend from explicit shell-owned values."""
        if not isinstance(output_is_terminal, bool):
            raise TypeError("output_is_terminal must be a boolean")
        if not output_is_terminal:
            raise WezTermPreflightError("stdout must be an interactive terminal")
        pane_id = parse_pane_id(environ)
        return cls(
            pane_id=pane_id,
            output=output,
            query_geometry=partial(query_pane_geometry, runner=runner),
        )

    def preflight(self) -> None:
        """Cache one required initial geometry before terminal mutation."""
        if self._terminal.cleanup_required or self._terminal.is_active:
            raise BackendStateError("preflight cannot run after terminal entry")
        if self._preflighted:
            return
        try:
            geometry = self._query_geometry(self._pane_id)
        except ViewportQueryError as error:
            raise WezTermPreflightError(f"WezTerm viewport preflight failed: {error}") from error
        if not isinstance(geometry, PaneGeometry) or geometry.pane_id != self._pane_id:
            raise WezTermPreflightError("viewport query returned the wrong pane geometry")
        self._geometry = geometry
        self._initial_pending = True
        self._preflighted = True

    def enter(self) -> None:
        """Activate terminal state after successful preflight."""
        if not self._preflighted or self._geometry is None:
            raise BackendStateError("backend must be preflighted before entry")
        self._terminal.enter()

    def get_viewport(self) -> Viewport | None:
        """Return cached initial geometry, then poll while retaining transient state."""
        if not self._preflighted or self._geometry is None:
            raise BackendStateError("backend must be preflighted before viewport access")
        if self._initial_pending:
            self._initial_pending = False
            return self._geometry.viewport
        try:
            candidate = self._query_geometry(self._pane_id)
        except ViewportQueryError:
            return None
        if not isinstance(candidate, PaneGeometry) or candidate.pane_id != self._pane_id:
            raise BackendStateError("viewport query returned the wrong pane geometry")
        self._geometry = candidate
        return candidate.viewport

    def present(self, frame: Frame) -> None:
        """Encode and stream one synchronized replacement without retaining it."""
        if not isinstance(frame, Frame):
            raise TypeError("frame must be a Frame")
        if not self._terminal.is_active or self._geometry is None:
            raise BackendStateError("presentation requires an active preflighted backend")
        viewport = self._geometry.viewport
        if (frame.width, frame.height) != (viewport.width_px, viewport.height_px):
            raise BackendStateError("frame dimensions must match the latest pane geometry")
        payload = self._frame_encoder(
            frame,
            columns=self._geometry.columns,
            rows=self._geometry.rows,
        )
        self._terminal.present((payload,))
        if self._presentation_pause:
            self._sleep(self._presentation_pause)

    def restore(self) -> None:
        """Idempotently restore all terminal state owned by this backend."""
        self._terminal.restore()
