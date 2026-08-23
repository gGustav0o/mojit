from __future__ import annotations

import io

import pytest

from mojit.application.input_text import InputTextError, resolve_input_text, validate_text


class PoisonStream(io.StringIO):
    def isatty(self) -> bool:
        raise AssertionError("stdin was inspected")

    def read(self, *args: object, **kwargs: object) -> str:
        raise AssertionError("stdin was read")


class TtyStream(io.StringIO):
    def isatty(self) -> bool:
        return True


class PipeStream(io.StringIO):
    def isatty(self) -> bool:
        return False


def test_positional_text_wins_without_touching_stdin() -> None:
    assert resolve_input_text(" 電脳世界 ", PoisonStream()) == " 電脳世界 "


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("猫\n", "猫"), ("猫\r\n", "猫"), ("猫  \n", "猫  "), ("猫", "猫")],
)
def test_pipe_removes_exactly_one_terminal_newline(raw: str, expected: str) -> None:
    assert resolve_input_text(None, PipeStream(raw)) == expected


def test_missing_text_on_tty_fails_without_reading() -> None:
    with pytest.raises(InputTextError, match="required"):
        resolve_input_text(None, TtyStream())


@pytest.mark.parametrize("text", ["", "   ", "\0", "a\nb", "a\rb", "猫\n\n"])
def test_invalid_single_line_text_is_rejected(text: str) -> None:
    with pytest.raises(InputTextError):
        validate_text(text, piped=text.endswith("\n"))


def test_text_length_is_measured_in_unicode_code_points() -> None:
    assert validate_text("猫" * 4096) == "猫" * 4096
    with pytest.raises(InputTextError, match="4096"):
        validate_text("猫" * 4097)


def test_invalid_utf8_decode_is_mapped() -> None:
    class BrokenStream(PipeStream):
        def read(self, size: int = -1) -> str:
            raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid")

    with pytest.raises(InputTextError, match="UTF-8"):
        resolve_input_text(None, BrokenStream())
