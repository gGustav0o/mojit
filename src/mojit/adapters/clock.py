"""Stateless stdlib clock satisfying the application runtime port."""

from __future__ import annotations

import time


class SystemMonotonicClock:
    """Use the high-resolution monotonic performance counter for scheduling."""

    __slots__ = ()

    def monotonic(self) -> float:
        return time.perf_counter()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)
