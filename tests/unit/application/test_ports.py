from __future__ import annotations

from mojit.application.ports import AnimationBackend, MonotonicClock
from mojit.core.models import Frame, Viewport


class _BackendWithoutInheritance:
    def get_viewport(self) -> Viewport | None:
        return Viewport(8, 6)

    def present(self, frame: Frame) -> None:
        del frame


class _ClockWithoutInheritance:
    def monotonic(self) -> float:
        return 0.0

    def sleep(self, seconds: float) -> None:
        del seconds


def _accept_backend(value: AnimationBackend) -> object:
    return value


def _accept_clock(value: MonotonicClock) -> object:
    return value


def test_ports_accept_structural_implementations_without_inheritance() -> None:
    backend = _BackendWithoutInheritance()
    clock = _ClockWithoutInheritance()
    assert _accept_backend(backend) is backend
    assert _accept_clock(clock) is clock
