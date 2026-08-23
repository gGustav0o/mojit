"""Pure fixed-step frame scheduling over explicit monotonic timestamps."""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real


class SchedulerContractError(ValueError):
    """Scheduler construction or method input violates its public contract."""


def _require_frame_index(value: object, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise SchedulerContractError(f"{name} must be >= 0")
    return value


def _require_timestamp(value: object, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number")
    converted = float(value)
    if not math.isfinite(converted):
        raise SchedulerContractError(f"{name} must be finite")
    return converted


@dataclass(frozen=True, slots=True)
class FixedStepScheduler:
    """Calculate absolute frame deadlines without reading or sleeping a clock."""

    fps: int
    started_at: float

    def __post_init__(self) -> None:
        if isinstance(self.fps, bool) or not isinstance(self.fps, int):
            raise TypeError("fps must be an integer")
        if not 1 <= self.fps <= 60:
            raise SchedulerContractError("fps must be between 1 and 60")
        object.__setattr__(
            self,
            "started_at",
            _require_timestamp(self.started_at, name="started_at"),
        )

    def elapsed_seconds(self, frame_index: int) -> float:
        """Return deterministic render time for one frame index."""
        index = _require_frame_index(frame_index, name="frame_index")
        try:
            elapsed = index / self.fps
        except OverflowError as error:
            raise SchedulerContractError("frame_index is too large") from error
        if not math.isfinite(elapsed):
            raise SchedulerContractError("frame elapsed time must be finite")
        return elapsed

    def deadline(self, frame_index: int) -> float:
        """Return the absolute monotonic deadline for one frame index."""
        deadline = self.started_at + self.elapsed_seconds(frame_index)
        if not math.isfinite(deadline):
            raise SchedulerContractError("frame deadline must be finite")
        return deadline

    def due_frame_index(self, now: float, minimum_index: int) -> int | None:
        """Return the latest due index at or above the minimum, or ``None`` if early."""
        timestamp = _require_timestamp(now, name="now")
        minimum = _require_frame_index(minimum_index, name="minimum_index")
        if timestamp < self.deadline(minimum):
            return None

        elapsed = max(0.0, timestamp - self.started_at)
        scaled_elapsed = elapsed * self.fps
        if not math.isfinite(scaled_elapsed):
            raise SchedulerContractError("due frame index must be finite")
        latest = max(minimum, math.floor(scaled_elapsed))

        # Correct the possible one-ULP loss at a deadline calculated by this class.
        while self.deadline(latest + 1) <= timestamp:
            latest += 1
        while latest > minimum and self.deadline(latest) > timestamp:
            latest -= 1
        return latest

    def delay_until(self, frame_index: int, now: float) -> float:
        """Return a non-negative delay until the frame deadline."""
        timestamp = _require_timestamp(now, name="now")
        return max(0.0, self.deadline(frame_index) - timestamp)
