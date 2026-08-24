from __future__ import annotations

import pytest

from mojit.adapters import budoux_segmenter
from mojit.adapters.budoux_segmenter import (
    JapaneseSegmentationError,
    segment_japanese_phrases,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("僕の心のヤバイやつ", ("僕の", "心の", "ヤバイや", "つ")),
        ("電脳世界", ("電脳世界",)),
        ("警告、「猫」。", ("警告、", "「猫」。")),
    ],
)
def test_default_model_returns_stable_immutable_phrases(
    text: str,
    expected: tuple[str, ...],
) -> None:
    phrases = segment_japanese_phrases(text)

    assert phrases == expected
    assert isinstance(phrases, tuple)
    assert "".join(phrases) == text


def test_model_loading_failure_is_mapped(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail() -> object:
        raise RuntimeError("model failed")

    monkeypatch.setattr("budoux.load_default_japanese_parser", fail)

    with pytest.raises(JapaneseSegmentationError, match="model") as captured:
        segment_japanese_phrases("猫")

    assert isinstance(captured.value.__cause__, RuntimeError)


def test_invalid_parser_output_is_mapped(monkeypatch: pytest.MonkeyPatch) -> None:
    class InvalidParser:
        def parse(self, text: str) -> list[str]:
            del text
            return ["別の文字列"]

    monkeypatch.setattr(budoux_segmenter, "_load_default_parser", InvalidParser)

    with pytest.raises(JapaneseSegmentationError, match="invalid") as captured:
        segment_japanese_phrases("猫")

    assert isinstance(captured.value.__cause__, ValueError)
