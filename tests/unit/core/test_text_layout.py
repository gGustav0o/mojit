from __future__ import annotations

import pytest

from mojit.core.text_layout import MAXIMUM_AUTO_LINES, horizontal_line_candidates


def test_original_line_is_always_the_first_candidate() -> None:
    candidates = horizontal_line_candidates("電脳世界")

    assert candidates[0] == ("電脳世界",)
    assert ("電脳", "世界") in candidates
    assert all("".join(lines) == "電脳世界" for lines in candidates)


def test_candidates_keep_combining_and_emoji_sequences_intact() -> None:
    combining = horizontal_line_candidates("A\u0301B")
    emoji = horizontal_line_candidates("👩‍💻猫")
    flag = horizontal_line_candidates("🇯🇵猫")
    indic = horizontal_line_candidates("क्ष猫")
    hangul = horizontal_line_candidates("한猫")

    assert combining == (("A\u0301B",), ("A\u0301", "B"))
    assert emoji == (("👩‍💻猫",), ("👩‍💻", "猫"))
    assert flag == (("🇯🇵猫",), ("🇯🇵", "猫"))
    assert indic == (("क्ष猫",), ("क्ष", "猫"))
    assert hangul == (("한猫",), ("한", "猫"))


def test_candidates_honor_japanese_prohibited_breaks() -> None:
    candidates = horizontal_line_candidates("「猫」、世界")

    assert ("「猫」、", "世界") in candidates
    assert all(not line.startswith(("」", "、")) for lines in candidates for line in lines)
    assert all(not line.endswith("「") for lines in candidates for line in lines)


def test_balancing_prefers_a_nearby_word_boundary() -> None:
    assert ("hello ", "world") in horizontal_line_candidates("hello world")


@pytest.mark.parametrize("separator", ["\u00a0", "\u202f", "\u2060", "\ufeff"])
def test_candidates_do_not_break_around_non_breaking_characters(separator: str) -> None:
    assert horizontal_line_candidates(f"a{separator}b") == ((f"a{separator}b",),)


def test_candidate_count_and_line_count_are_bounded() -> None:
    candidates = horizontal_line_candidates("猫" * 64)

    assert len(candidates) == MAXIMUM_AUTO_LINES
    assert max(map(len, candidates)) == MAXIMUM_AUTO_LINES
    assert len(set(candidates)) == len(candidates)


@pytest.mark.parametrize("maximum_lines", [0, -1, True, 1.5])
def test_maximum_lines_must_be_a_positive_integer(maximum_lines: object) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        horizontal_line_candidates("猫", maximum_lines=maximum_lines)  # type: ignore[arg-type]
