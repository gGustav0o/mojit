"""Structural runtime ports owned by application orchestration."""

from __future__ import annotations

from typing import Protocol

from mojit.core.models import Frame, Viewport


class AnimationBackend(Protocol):
    """Narrow viewport and presentation boundary used by the animation loop."""

    def get_viewport(self) -> Viewport | None:
        """Return the current viewport or ``None`` for a transient poll failure."""
        ...

    def present(self, frame: Frame) -> None:
        """Present one complete immutable frame."""
        ...


class MonotonicClock(Protocol):
    """Clock operations required by fixed-step runtime scheduling."""

    def monotonic(self) -> float:
        """Return a finite non-decreasing timestamp in seconds."""
        ...

    def sleep(self, seconds: float) -> None:
        """Wait for a finite non-negative duration."""
        ...
