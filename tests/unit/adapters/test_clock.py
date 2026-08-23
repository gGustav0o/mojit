from __future__ import annotations

from mojit.adapters import clock as clock_module
from mojit.adapters.clock import SystemMonotonicClock


def test_system_clock_delegates_to_high_resolution_monotonic_functions(monkeypatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr(clock_module.time, "perf_counter", lambda: 12.5)
    monkeypatch.setattr(clock_module.time, "sleep", sleeps.append)

    clock = SystemMonotonicClock()
    assert clock.monotonic() == 12.5
    clock.sleep(0.25)
    assert sleeps == [0.25]
