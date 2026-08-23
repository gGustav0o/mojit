from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from mojit.application.scheduler import FixedStepScheduler, SchedulerContractError


def test_scheduler_is_frozen_and_normalizes_start_timestamp() -> None:
    scheduler = FixedStepScheduler(fps=30, started_at=5)
    assert scheduler.started_at == 5.0
    with pytest.raises(FrozenInstanceError):
        scheduler.fps = 60  # type: ignore[misc]


def test_deadlines_and_elapsed_are_absolute_and_index_derived() -> None:
    scheduler = FixedStepScheduler(fps=20, started_at=10.25)
    assert scheduler.elapsed_seconds(0) == 0.0
    assert scheduler.elapsed_seconds(7) == 0.35
    assert scheduler.deadline(0) == 10.25
    assert scheduler.deadline(7) == 10.6
    assert scheduler.deadline(10_000) == 10.25 + 10_000 / 20


def test_due_frame_is_none_before_minimum_deadline() -> None:
    scheduler = FixedStepScheduler(fps=10, started_at=2.0)
    assert scheduler.due_frame_index(2.099, 1) is None
    assert scheduler.due_frame_index(2.4, 5) is None


def test_due_frame_selects_exact_boundary_and_latest_late_index() -> None:
    scheduler = FixedStepScheduler(fps=10, started_at=2.0)
    assert scheduler.due_frame_index(scheduler.deadline(0), 0) == 0
    assert scheduler.due_frame_index(scheduler.deadline(7), 1) == 7
    assert scheduler.due_frame_index(2.799, 1) == 7


def test_due_frame_never_rewinds_below_minimum() -> None:
    scheduler = FixedStepScheduler(fps=10, started_at=0.0)
    assert scheduler.due_frame_index(0.499, 5) is None
    assert scheduler.due_frame_index(0.5, 5) == 5


def test_delay_is_positive_when_early_and_zero_when_due() -> None:
    scheduler = FixedStepScheduler(fps=4, started_at=1.0)
    assert scheduler.delay_until(1, 1.1) == pytest.approx(0.15)
    assert scheduler.delay_until(1, 1.25) == 0.0
    assert scheduler.delay_until(1, 2.0) == 0.0


@pytest.mark.parametrize("fps", [True, 1.0, "30"])
def test_scheduler_rejects_non_integer_fps(fps: object) -> None:
    with pytest.raises(TypeError, match="fps must be an integer"):
        FixedStepScheduler(fps=fps, started_at=0.0)  # type: ignore[arg-type]


@pytest.mark.parametrize("fps", [0, 61, -1])
def test_scheduler_rejects_out_of_range_fps(fps: int) -> None:
    with pytest.raises(SchedulerContractError, match="between 1 and 60"):
        FixedStepScheduler(fps=fps, started_at=0.0)


@pytest.mark.parametrize("started_at", [True, "0", float("nan"), float("inf")])
def test_scheduler_rejects_invalid_start_timestamp(started_at: object) -> None:
    with pytest.raises((TypeError, SchedulerContractError)):
        FixedStepScheduler(fps=30, started_at=started_at)  # type: ignore[arg-type]


@pytest.mark.parametrize("index", [True, 1.5, -1])
def test_scheduler_rejects_invalid_frame_indices(index: object) -> None:
    scheduler = FixedStepScheduler(fps=30, started_at=0.0)
    with pytest.raises((TypeError, SchedulerContractError)):
        scheduler.deadline(index)  # type: ignore[arg-type]
    with pytest.raises((TypeError, SchedulerContractError)):
        scheduler.due_frame_index(1.0, index)  # type: ignore[arg-type]


@pytest.mark.parametrize("now", [True, "1", float("nan"), float("-inf")])
def test_scheduler_rejects_invalid_current_timestamp(now: object) -> None:
    scheduler = FixedStepScheduler(fps=30, started_at=0.0)
    with pytest.raises((TypeError, SchedulerContractError)):
        scheduler.due_frame_index(now, 0)  # type: ignore[arg-type]
    with pytest.raises((TypeError, SchedulerContractError)):
        scheduler.delay_until(0, now)  # type: ignore[arg-type]


def test_scheduler_rejects_numeric_overflow() -> None:
    scheduler = FixedStepScheduler(fps=60, started_at=0.0)
    with pytest.raises(SchedulerContractError, match="too large"):
        scheduler.elapsed_seconds(10**1000)
    with pytest.raises(SchedulerContractError, match="due frame index"):
        scheduler.due_frame_index(float.fromhex("0x1.fffffffffffffp+1023"), 0)
