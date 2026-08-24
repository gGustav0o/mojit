"""BudouX boundary for immutable Japanese phrase segmentation."""

from __future__ import annotations

from typing import Protocol

from mojit.core.text_layout import TextPhrases, validate_text_phrases


class JapaneseSegmentationError(ValueError):
    """The configured Japanese phrase model could not segment the input."""


class _JapaneseParser(Protocol):
    def parse(self, text: str) -> list[str]: ...


def _load_default_parser() -> _JapaneseParser:
    try:
        from budoux import load_default_japanese_parser

        return load_default_japanese_parser()
    except Exception as error:  # third-party boundary
        raise JapaneseSegmentationError("cannot load the BudouX Japanese model") from error


def segment_japanese_phrases(text: str) -> TextPhrases:
    """Parse one string once and return a validated immutable partition."""
    parser = _load_default_parser()
    try:
        phrases = tuple(parser.parse(text))
        validate_text_phrases(text, phrases)
    except Exception as error:  # third-party output is untrusted
        raise JapaneseSegmentationError("BudouX returned invalid Japanese phrases") from error
    return phrases
