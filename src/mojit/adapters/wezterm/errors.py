"""Typed operational failures for the production WezTerm adapter."""

from __future__ import annotations


class WezTermAdapterError(RuntimeError):
    """Base class for operational failures in the WezTerm shell."""


class WezTermPreflightError(WezTermAdapterError):
    """The process cannot safely enter production terminal mode."""


class ViewportQueryError(WezTermAdapterError):
    """The current pane geometry could not be acquired or validated."""


class PngEncodingError(WezTermAdapterError):
    """A frame could not be encoded as PNG."""


class KittyProtocolError(WezTermAdapterError):
    """Kitty protocol values cannot be encoded safely."""


class TerminalStateError(WezTermAdapterError):
    """A terminal lifecycle operation is invalid in the current state."""


class TerminalOutputError(WezTermAdapterError):
    """Terminal-control bytes could not be written or flushed."""


class BackendStateError(WezTermAdapterError):
    """The concrete backend was used out of lifecycle order."""
