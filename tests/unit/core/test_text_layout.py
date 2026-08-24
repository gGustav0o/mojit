from __future__ import annotations

import pytest

from mojit.core.text_layout import MAXIMUM_AUTO_LINES, horizontal_line_candidates


def test_candidates_use_only_phrase_boundaries_and_preserve_text() -> None:
    text = "僕の心のヤバイやつ"
    phrases = ("僕の", "心の", "ヤバイや", "つ")

    candidates = horizontal_line_candidates(text, phrases=phrases)

    assert candidates[0] == (text,)
    assert ("僕の心の", "ヤバイやつ") in candidates
    assert ("僕の", "心の", "ヤバイやつ") in candidates
    assert all("".join(lines) == text for lines in candidates)
    assert all("つ" not in lines for lines in candidates if len(lines) > 1)


@pytest.mark.parametrize(
    ("text", "phrases"),
    [
        ("A\u0301BBBBBBBB", ("A", "\u0301BBB", "BBBBB")),
        ("👩‍💻猫猫猫猫", ("👩", "\u200d💻猫", "猫猫猫")),
        ("🇯🇵猫猫猫猫", ("🇯", "🇵猫", "猫猫猫")),
        ("क्ष猫猫猫猫", ("क", "्ष猫", "猫猫猫")),
        ("한猫猫猫猫", ("ᄒ", "ᅡᆫ猫", "猫猫猫")),
    ],
)
def test_candidates_ignore_phrase_boundaries_inside_unicode_clusters(
    text: str,
    phrases: tuple[str, ...],
) -> None:
    candidates = horizontal_line_candidates(text, phrases=phrases)

    assert all(lines[0] != phrases[0] for lines in candidates if len(lines) > 1)
    assert all("".join(lines) == text for lines in candidates)


def test_candidates_honor_japanese_prohibited_breaks() -> None:
    text = "「猫」、世界"
    candidates = horizontal_line_candidates(text, phrases=("「", "猫", "」、", "世界"))

    assert ("「猫」、", "世界") in candidates
    assert all(not line.startswith(("」", "、")) for lines in candidates for line in lines)
    assert all(not line.endswith("「") for lines in candidates for line in lines)


@pytest.mark.parametrize("separator", ["\u00a0", "\u202f", "\u2060", "\ufeff"])
def test_candidates_do_not_break_around_non_breaking_characters(separator: str) -> None:
    text = f"aaaa{separator}bbbb"

    assert horizontal_line_candidates(
        text,
        phrases=("aaaa", separator, "bbbb"),
    ) == ((text,),)


def test_candidate_count_and_line_count_are_bounded() -> None:
    text = "猫" * 64
    candidates = horizontal_line_candidates(text, phrases=("猫",) * 64)

    assert len(candidates) == MAXIMUM_AUTO_LINES
    assert max(map(len, candidates)) == MAXIMUM_AUTO_LINES
    assert len(set(candidates)) == len(candidates)


@pytest.mark.parametrize(
    "phrases",
    [(), ["電脳世界"], ("", "電脳世界"), ("電脳", "世界観")],
)
def test_phrases_must_be_an_immutable_exact_partition(phrases: object) -> None:
    with pytest.raises((TypeError, ValueError), match="phrases"):
        horizontal_line_candidates("電脳世界", phrases=phrases)  # type: ignore[arg-type]


@pytest.mark.parametrize("maximum_lines", [0, -1, True, 1.5])
def test_maximum_lines_must_be_a_positive_integer(maximum_lines: object) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        horizontal_line_candidates(
            "猫",
            phrases=("猫",),
            maximum_lines=maximum_lines,  # type: ignore[arg-type]
        )
