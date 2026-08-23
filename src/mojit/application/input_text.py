"""Text-input policy and the minimal stdin shell."""

from __future__ import annotations

from typing import TextIO

MAX_TEXT_CODEPOINTS = 4096


class InputTextError(ValueError):
    """Text input cannot be used as one renderable line."""


def validate_text(value: object, *, piped: bool = False) -> str:
    """Normalize one pipeline newline and validate one Unicode text line."""
    if not isinstance(value, str):
        raise InputTextError("text must be Unicode text")

    text = value
    if piped:
        if text.endswith("\r\n"):
            text = text[:-2]
        elif text.endswith("\n"):
            text = text[:-1]

    if not text or text.isspace():
        raise InputTextError("text must contain at least one visible character")
    if "\0" in text:
        raise InputTextError("text must not contain NUL")
    if "\r" in text or "\n" in text:
        raise InputTextError("text must be a single line")
    if len(text) > MAX_TEXT_CODEPOINTS:
        raise InputTextError(f"text must not exceed {MAX_TEXT_CODEPOINTS} code points")
    return text


def resolve_input_text(positional: str | None, stdin: TextIO) -> str:
    """Prefer positional text and otherwise perform one bounded stdin read."""
    if positional is not None:
        return validate_text(positional)
    if stdin.isatty():
        raise InputTextError("text is required as an argument or piped UTF-8 input")
    try:
        text = stdin.read(MAX_TEXT_CODEPOINTS + 3)
    except UnicodeDecodeError as error:
        raise InputTextError("stdin is not valid UTF-8") from error
    return validate_text(text, piped=True)
