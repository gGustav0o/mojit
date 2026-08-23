"""Concrete production composition for viewport, PNG, Kitty, and terminal state."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from functools import partial
from typing import BinaryIO

from mojit.adapters.wezterm.errors import (
    BackendStateError,
    ViewportQueryError,
    WezTermPreflightError,
)
from mojit.adapters.wezterm.kitty_protocol import iter_transmit_png, make_image_id
from mojit.adapters.wezterm.png_encoder import encode_frame_png
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
PngEncoder = Callable[[Frame], bytes]


class WezTermBackend:
    """Implement the Phase 4 backend port without importing application."""

    __slots__ = (
        "_geometry",
        "_image_id",
        "_initial_pending",
        "_pane_id",
        "_png_encoder",
        "_preflighted",
        "_query_geometry",
        "_terminal",
    )

    def __init__(
        self,
        *,
        pane_id: int,
        output: BinaryIO,
        image_id: int,
        query_geometry: GeometryQuery,
        png_encoder: PngEncoder = encode_frame_png,
    ) -> None:
        if isinstance(pane_id, bool) or not isinstance(pane_id, int) or pane_id < 0:
            raise TypeError("pane_id must be a non-negative integer")
        if not callable(query_geometry):
            raise TypeError("query_geometry must be callable")
        if not callable(png_encoder):
            raise TypeError("png_encoder must be callable")
        self._pane_id = pane_id
        self._image_id = image_id
        self._query_geometry = query_geometry
        self._png_encoder = png_encoder
        self._terminal = TerminalSession(output, image_id=image_id)
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
        process_id: int | None = None,
        runner: Runner = run_wezterm_cli,
    ) -> WezTermBackend:
        """Build one process backend from explicit shell-owned values."""
        if not isinstance(output_is_terminal, bool):
            raise TypeError("output_is_terminal must be a boolean")
        if not output_is_terminal:
            raise WezTermPreflightError("stdout must be an interactive terminal")
        pane_id = parse_pane_id(environ)
        pid = os.getpid() if process_id is None else process_id
        return cls(
            pane_id=pane_id,
            output=output,
            image_id=make_image_id(pid),
            query_geometry=partial(query_pane_geometry, runner=runner),
        )

    @property
    def image_id(self) -> int:
        return self._image_id

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
        payload = self._png_encoder(frame)
        commands = iter_transmit_png(
            payload,
            image_id=self._image_id,
            width=frame.width,
            height=frame.height,
            columns=self._geometry.columns,
            rows=self._geometry.rows,
        )
        self._terminal.present(commands)

    def restore(self) -> None:
        """Idempotently restore all terminal state owned by this backend."""
        self._terminal.restore()
