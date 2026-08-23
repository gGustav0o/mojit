from __future__ import annotations

from collections.abc import Iterable

import pytest

from mojit.adapters.wezterm.errors import TerminalOutputError, TerminalStateError
from mojit.adapters.wezterm.kitty_protocol import delete_image
from mojit.adapters.wezterm.terminal_state import (
    BEGIN_SYNCHRONIZED_UPDATE,
    CURSOR_HOME,
    END_SYNCHRONIZED_UPDATE,
    ENTER_TERMINAL,
    LEAVE_ALTERNATE_SCREEN,
    SHOW_CURSOR,
    TerminalSession,
)


class RecordingOutput:
    def __init__(self, *, max_chunk: int | None = None) -> None:
        self.data = bytearray()
        self.flushes = 0
        self.max_chunk = max_chunk
        self.write_failure: Exception | None = None
        self.flush_failure: Exception | None = None
        self.closed = False

    def write(self, value: bytes | memoryview) -> int:
        if self.write_failure is not None:
            raise self.write_failure
        raw = bytes(value)
        length = len(raw) if self.max_chunk is None else min(len(raw), self.max_chunk)
        self.data.extend(raw[:length])
        return length

    def flush(self) -> None:
        self.flushes += 1
        if self.flush_failure is not None:
            raise self.flush_failure


def _cleanup(image_id: int) -> bytes:
    return END_SYNCHRONIZED_UPDATE + delete_image(image_id) + SHOW_CURSOR + LEAVE_ALTERNATE_SCREEN


def test_complete_lifecycle_emits_exact_bytes_and_flushes() -> None:
    output = RecordingOutput()
    session = TerminalSession(output, image_id=17)  # type: ignore[arg-type]

    session.enter()
    session.present([b"first", b"second"])
    session.restore()

    assert bytes(output.data) == (
        ENTER_TERMINAL
        + BEGIN_SYNCHRONIZED_UPDATE
        + CURSOR_HOME
        + b"firstsecond"
        + END_SYNCHRONIZED_UPDATE
        + _cleanup(17)
    )
    assert output.flushes == 3
    assert session.is_active is False
    assert session.cleanup_required is False
    assert output.closed is False


def test_partial_writes_are_completed_without_data_loss() -> None:
    output = RecordingOutput(max_chunk=2)
    session = TerminalSession(output, image_id=23)  # type: ignore[arg-type]

    session.enter()
    session.present([b"payload"])
    session.restore()

    assert bytes(output.data).startswith(ENTER_TERMINAL + BEGIN_SYNCHRONIZED_UPDATE)
    assert bytes(output.data).endswith(_cleanup(23))


def test_restore_is_noop_before_entry_and_after_success() -> None:
    output = RecordingOutput()
    session = TerminalSession(output, image_id=29)  # type: ignore[arg-type]

    session.restore()
    assert output.data == b""
    assert output.flushes == 0

    session.enter()
    session.restore()
    restored = bytes(output.data)
    session.restore()

    assert bytes(output.data) == restored
    assert output.flushes == 2


def test_failed_entry_remains_cleanup_eligible() -> None:
    output = RecordingOutput()
    output.flush_failure = OSError("flush")
    session = TerminalSession(output, image_id=31)  # type: ignore[arg-type]

    with pytest.raises(TerminalOutputError, match="flush"):
        session.enter()

    assert session.cleanup_required is True
    output.flush_failure = None
    session.restore()
    assert bytes(output.data).endswith(_cleanup(31))


def test_failed_presentation_remains_cleanup_eligible() -> None:
    output = RecordingOutput()
    session = TerminalSession(output, image_id=37)  # type: ignore[arg-type]
    session.enter()

    def commands() -> Iterable[bytes]:
        yield b"partial"
        raise RuntimeError("producer failed")

    with pytest.raises(RuntimeError, match="producer failed"):
        session.present(commands())

    assert session.cleanup_required is True
    session.restore()
    assert bytes(output.data).endswith(_cleanup(37))


def test_failed_restore_is_retryable() -> None:
    output = RecordingOutput()
    session = TerminalSession(output, image_id=41)  # type: ignore[arg-type]
    session.enter()
    output.write_failure = OSError("write")

    with pytest.raises(TerminalOutputError, match="write"):
        session.restore()

    assert session.cleanup_required is True
    output.write_failure = None
    session.restore()
    assert bytes(output.data).endswith(_cleanup(41))


class InvalidProgressOutput(RecordingOutput):
    def __init__(self, progress: object) -> None:
        super().__init__()
        self.progress = progress

    def write(self, value: bytes | memoryview) -> object:
        return self.progress


@pytest.mark.parametrize("progress", [None, True, 0, -1, 10_000])
def test_invalid_write_progress_is_rejected(progress: object) -> None:
    session = TerminalSession(InvalidProgressOutput(progress), image_id=43)  # type: ignore[arg-type]
    with pytest.raises(TerminalOutputError, match="write progress|write length"):
        session.enter()
    assert session.cleanup_required is True


def test_state_machine_rejects_invalid_order_and_commands() -> None:
    output = RecordingOutput()
    session = TerminalSession(output, image_id=47)  # type: ignore[arg-type]

    with pytest.raises(TerminalStateError, match="active"):
        session.present([b"x"])

    session.enter()
    with pytest.raises(TerminalStateError, match="entered once"):
        session.enter()
    with pytest.raises(TerminalStateError, match="non-empty"):
        session.present([b""])

    session.restore()
    with pytest.raises(TerminalStateError, match="active"):
        session.present([b"x"])


@pytest.mark.parametrize("output", [object(), None])
def test_constructor_requires_binary_output_contract(output: object) -> None:
    with pytest.raises(TypeError, match="write and flush"):
        TerminalSession(output, image_id=1)  # type: ignore[arg-type]
