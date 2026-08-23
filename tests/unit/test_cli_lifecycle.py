from __future__ import annotations

import io
from dataclasses import dataclass, field

import pytest

from mojit import cli as cli_module
from mojit.adapters.wezterm.errors import WezTermPreflightError
from mojit.cli import LifecycleFailure, execute_prepared_run, main


@dataclass
class FakeBackend:
    events: list[str] = field(default_factory=list)
    preflight_failure: BaseException | None = None
    enter_failure: BaseException | None = None
    restore_failure: BaseException | None = None

    def preflight(self) -> None:
        self.events.append("preflight")
        if self.preflight_failure is not None:
            raise self.preflight_failure

    def enter(self) -> None:
        self.events.append("enter")
        if self.enter_failure is not None:
            raise self.enter_failure

    def restore(self) -> None:
        self.events.append("restore")
        if self.restore_failure is not None:
            raise self.restore_failure


def _execute(
    monkeypatch: pytest.MonkeyPatch,
    backend: FakeBackend,
    runtime_failure: BaseException | None = None,
) -> None:
    def run(*args: object, **kwargs: object) -> None:
        backend.events.append("run")
        if runtime_failure is not None:
            raise runtime_failure

    monkeypatch.setattr(cli_module, "run_animation", run)
    execute_prepared_run(
        object(),  # type: ignore[arg-type]
        backend=backend,  # type: ignore[arg-type]
        clock=object(),  # type: ignore[arg-type]
    )


def test_execute_orders_preflight_runtime_and_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = FakeBackend()
    _execute(monkeypatch, backend)
    assert backend.events == ["preflight", "enter", "run", "restore"]


def test_preflight_failure_does_not_attempt_terminal_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = WezTermPreflightError("preflight")
    backend = FakeBackend(preflight_failure=failure)
    with pytest.raises(WezTermPreflightError) as captured:
        _execute(monkeypatch, backend)
    assert captured.value is failure
    assert backend.events == ["preflight"]


@pytest.mark.parametrize("stage", ["enter", "runtime"])
def test_primary_failure_is_rethrown_after_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    failure = RuntimeError(stage)
    backend = FakeBackend(enter_failure=failure if stage == "enter" else None)
    with pytest.raises(RuntimeError) as captured:
        _execute(monkeypatch, backend, failure if stage == "runtime" else None)
    assert captured.value is failure
    assert backend.events[-1] == "restore"


def test_keyboard_interrupt_is_normal_exit_after_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = FakeBackend()
    _execute(monkeypatch, backend, KeyboardInterrupt())
    assert backend.events == ["preflight", "enter", "run", "restore"]


def test_cleanup_failure_retains_both_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    primary = RuntimeError("runtime")
    cleanup = OSError("cleanup")
    backend = FakeBackend(restore_failure=cleanup)

    with pytest.raises(LifecycleFailure) as captured:
        _execute(monkeypatch, backend, primary)

    assert captured.value.primary is primary
    assert captured.value.cleanup is cleanup
    assert "runtime failed" in str(captured.value)
    assert "cleanup also failed" in str(captured.value)


def test_cleanup_only_failure_is_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    cleanup = OSError("cleanup")
    backend = FakeBackend(restore_failure=cleanup)

    with pytest.raises(LifecycleFailure) as captured:
        _execute(monkeypatch, backend)

    assert captured.value.primary is None
    assert captured.value.cleanup is cleanup
    assert "terminal cleanup failed" in str(captured.value)


def test_interrupt_plus_cleanup_failure_is_exit_one(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    request = object()
    backend = FakeBackend(restore_failure=OSError("cleanup"))
    monkeypatch.setattr(cli_module, "prepare_run", lambda *args, **kwargs: request)
    monkeypatch.setattr(cli_module, "_create_backend", lambda *args, **kwargs: backend)
    monkeypatch.setattr(
        cli_module,
        "run_animation",
        lambda *args, **kwargs: (_ for _ in ()).throw(KeyboardInterrupt()),
    )

    assert main(["猫"]) == 1
    captured = capsys.readouterr()
    assert "cleanup also failed" in captured.err
    assert "Traceback" not in captured.err


def test_main_success_builds_backend_and_executes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = object()
    backend = object()
    observed: dict[str, object] = {}

    monkeypatch.setattr(cli_module, "prepare_run", lambda *args, **kwargs: request)
    monkeypatch.setattr(cli_module, "_create_backend", lambda *args, **kwargs: backend)

    def execute(value: object, *, backend: object, clock: object) -> None:
        observed.update(request=value, backend=backend, clock=clock)

    monkeypatch.setattr(cli_module, "execute_prepared_run", execute)
    assert main(["猫"]) == 0
    assert observed["request"] is request
    assert observed["backend"] is backend
    assert observed["clock"].__class__.__name__ == "SystemMonotonicClock"


class TextOutputWithoutBuffer(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_backend_creation_requires_binary_stdout() -> None:
    with pytest.raises(WezTermPreflightError, match="binary"):
        cli_module._create_backend({"WEZTERM_PANE": "2"}, TextOutputWithoutBuffer())
