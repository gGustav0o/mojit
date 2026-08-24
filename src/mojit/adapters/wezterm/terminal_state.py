"""Binary terminal state machine with idempotent, retryable cleanup."""

from __future__ import annotations

from collections.abc import Iterable
from enum import Enum, auto
from typing import BinaryIO

from mojit.adapters.wezterm.errors import TerminalOutputError, TerminalStateError

ESC = b"\x1b"
ENTER_TERMINAL = ESC + b"[?1049h" + ESC + b"[2J" + ESC + b"[H" + ESC + b"[?25l"
BEGIN_SYNCHRONIZED_UPDATE = ESC + b"[?2026h"
END_SYNCHRONIZED_UPDATE = ESC + b"[?2026l"
CURSOR_HOME = ESC + b"[H"
RESET_ATTRIBUTES = ESC + b"[0m"
SHOW_CURSOR = ESC + b"[?25h"
LEAVE_ALTERNATE_SCREEN = ESC + b"[?1049l"


class _LifecycleState(Enum):
    NEW = auto()
    DIRTY = auto()
    ACTIVE = auto()
    RESTORED = auto()


class TerminalSession:
    """Own all terminal mutations for one process image."""

    __slots__ = ("_output", "_state")

    def __init__(self, output: BinaryIO) -> None:
        if not callable(getattr(output, "write", None)) or not callable(
            getattr(output, "flush", None)
        ):
            raise TypeError("output must provide binary write and flush methods")
        self._output = output
        self._state = _LifecycleState.NEW

    @property
    def is_active(self) -> bool:
        return self._state is _LifecycleState.ACTIVE

    @property
    def cleanup_required(self) -> bool:
        return self._state in {_LifecycleState.DIRTY, _LifecycleState.ACTIVE}

    def _write_exact(self, data: bytes) -> None:
        if not isinstance(data, bytes) or not data:
            raise TerminalStateError("terminal command must be non-empty bytes")
        view = memoryview(data)
        offset = 0
        try:
            while offset < len(view):
                written = self._output.write(view[offset:])
                if isinstance(written, bool) or not isinstance(written, int) or written <= 0:
                    raise TerminalOutputError("terminal output made no write progress")
                if written > len(view) - offset:
                    raise TerminalOutputError("terminal output reported an invalid write length")
                offset += written
        except TerminalOutputError:
            raise
        except Exception as error:
            raise TerminalOutputError(f"terminal write failed: {error}") from error

    def _flush(self) -> None:
        try:
            self._output.flush()
        except Exception as error:
            raise TerminalOutputError(f"terminal flush failed: {error}") from error

    def enter(self) -> None:
        """Enter the alternate screen and hide the cursor exactly once."""
        if self._state is not _LifecycleState.NEW:
            raise TerminalStateError("terminal session can only be entered once")
        self._state = _LifecycleState.DIRTY
        self._write_exact(ENTER_TERMINAL)
        self._flush()
        self._state = _LifecycleState.ACTIVE

    def present(self, commands: Iterable[bytes]) -> None:
        """Write one synchronized cell replacement and flush once."""
        if self._state is not _LifecycleState.ACTIVE:
            raise TerminalStateError("terminal presentation requires an active session")
        if not isinstance(commands, Iterable):
            raise TypeError("commands must be iterable")

        self._state = _LifecycleState.DIRTY
        self._write_exact(BEGIN_SYNCHRONIZED_UPDATE)
        self._write_exact(CURSOR_HOME)
        for command in commands:
            self._write_exact(command)
        self._write_exact(END_SYNCHRONIZED_UPDATE)
        self._flush()
        self._state = _LifecycleState.ACTIVE

    def restore(self) -> None:
        """Restore every owned state; successful repeated calls are no-ops."""
        if self._state in {_LifecycleState.NEW, _LifecycleState.RESTORED}:
            return
        self._state = _LifecycleState.DIRTY
        cleanup = END_SYNCHRONIZED_UPDATE + RESET_ATTRIBUTES + SHOW_CURSOR + LEAVE_ALTERNATE_SCREEN
        self._write_exact(cleanup)
        self._flush()
        self._state = _LifecycleState.RESTORED
