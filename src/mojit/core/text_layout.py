"""Pure Unicode-aware candidates for automatic horizontal line breaking."""

from __future__ import annotations

import unicodedata
from bisect import bisect_left
from itertools import pairwise

TextLines = tuple[str, ...]

MAXIMUM_AUTO_LINES = 16

_PROHIBITED_LINE_START = frozenset(
    ")]}〉》」』】〕〗〙〟｝）］、。，．・：；？！ー〜～…‥’”｠»"
    "ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮヵヶ々〻ゝゞヽヾ"
)
_PROHIBITED_LINE_END = frozenset("([{〈《「『【〔〖〘〝｛（［‘“｟«")
_NON_BREAKING_CHARACTERS = frozenset("\u00a0\u202f\u2060\ufeff")
_ZERO_WIDTH_JOINER = "\u200d"
_ZERO_WIDTH_NON_JOINER = "\u200c"


def _is_variation_selector(character: str) -> bool:
    codepoint = ord(character)
    return 0xFE00 <= codepoint <= 0xFE0F or 0xE0100 <= codepoint <= 0xE01EF


def _is_emoji_modifier(character: str) -> bool:
    codepoint = ord(character)
    return 0x1F3FB <= codepoint <= 0x1F3FF or 0xE0020 <= codepoint <= 0xE007F


def _is_regional_indicator(character: str) -> bool:
    return 0x1F1E6 <= ord(character) <= 0x1F1FF


def _is_extending_character(character: str) -> bool:
    return (
        unicodedata.category(character) in {"Mc", "Me", "Mn"}
        or character == _ZERO_WIDTH_NON_JOINER
        or _is_variation_selector(character)
        or _is_emoji_modifier(character)
    )


def _ends_with_virama(cluster: str) -> bool:
    for character in reversed(cluster):
        if character == _ZERO_WIDTH_JOINER:
            continue
        if not _is_extending_character(character):
            return False
        if unicodedata.combining(character) == 9:
            return True
    return False


def _visible_edge(cluster: str, *, from_end: bool = False) -> str:
    characters = reversed(cluster) if from_end else iter(cluster)
    for character in characters:
        if character != _ZERO_WIDTH_JOINER and not _is_extending_character(character):
            return character
    return cluster[-1 if from_end else 0]


def _hangul_type(character: str) -> str | None:
    codepoint = ord(character)
    if 0x1100 <= codepoint <= 0x115F or 0xA960 <= codepoint <= 0xA97C:
        return "L"
    if 0x1160 <= codepoint <= 0x11A7 or 0xD7B0 <= codepoint <= 0xD7C6:
        return "V"
    if 0x11A8 <= codepoint <= 0x11FF or 0xD7CB <= codepoint <= 0xD7FB:
        return "T"
    if 0xAC00 <= codepoint <= 0xD7A3:
        return "LV" if (codepoint - 0xAC00) % 28 == 0 else "LVT"
    return None


def _joins_hangul_sequence(cluster: str, character: str) -> bool:
    previous_type = _hangul_type(_visible_edge(cluster, from_end=True))
    current_type = _hangul_type(character)
    return (
        previous_type == "L"
        and current_type in {"L", "V", "LV", "LVT"}
        or previous_type in {"LV", "V"}
        and current_type in {"V", "T"}
        or previous_type in {"LVT", "T"}
        and current_type == "T"
    )


def _text_clusters(text: str) -> tuple[str, ...]:
    """Keep combining sequences, emoji modifiers, ZWJ sequences, and flags intact."""
    clusters: list[str] = []
    current = ""
    regional_indicators = 0

    for character in text:
        if not current:
            current = character
            regional_indicators = int(_is_regional_indicator(character))
            continue

        joins_current = (
            _is_extending_character(character)
            or character == _ZERO_WIDTH_JOINER
            or current.endswith(_ZERO_WIDTH_JOINER)
            or _ends_with_virama(current)
            or _joins_hangul_sequence(current, character)
            or (_is_regional_indicator(character) and regional_indicators == 1)
        )
        if joins_current:
            current += character
            if _is_regional_indicator(character):
                regional_indicators += 1
            continue

        clusters.append(current)
        current = character
        regional_indicators = int(_is_regional_indicator(character))

    if current:
        clusters.append(current)
    return tuple(clusters)


def _safe_boundary(clusters: tuple[str, ...], index: int) -> bool:
    previous = _visible_edge(clusters[index - 1], from_end=True)
    following = _visible_edge(clusters[index])
    return (
        previous not in _PROHIBITED_LINE_END
        and following not in _PROHIBITED_LINE_START
        and previous not in _NON_BREAKING_CHARACTERS
        and following not in _NON_BREAKING_CHARACTERS
    )


def _cluster_weight(cluster: str) -> int:
    """Approximate relative advance without depending on a font or renderer."""
    visible = (
        character
        for character in cluster
        if character != _ZERO_WIDTH_JOINER and not _is_extending_character(character)
    )
    return (
        2
        if any(unicodedata.east_asian_width(character) in {"F", "W"} for character in visible)
        else 1
    )


def _natural_boundary(clusters: tuple[str, ...], index: int) -> bool:
    previous = _visible_edge(clusters[index - 1], from_end=True)
    following = _visible_edge(clusters[index])
    return previous.isspace() or (
        unicodedata.east_asian_width(previous) in {"F", "W"}
        or unicodedata.east_asian_width(following) in {"F", "W"}
    )


def _balanced_boundaries(
    clusters: tuple[str, ...],
    boundaries: tuple[int, ...],
    line_count: int,
) -> tuple[int, ...]:
    cumulative = [0]
    for cluster in clusters:
        cumulative.append(cumulative[-1] + _cluster_weight(cluster))
    total_weight = cumulative[-1]

    selected: list[int] = []
    previous_position = -1
    for part in range(1, line_count):
        remaining_cuts = line_count - part - 1
        first_position = previous_position + 1
        last_position = len(boundaries) - remaining_cuts - 1
        choices = boundaries[first_position : last_position + 1]

        distances = {
            boundary: abs(cumulative[boundary] * line_count - total_weight * part)
            for boundary in choices
        }
        nearby_natural = tuple(
            boundary
            for boundary in choices
            if _natural_boundary(clusters, boundary)
            and distances[boundary] <= max(1, total_weight // 2)
        )
        pool = nearby_natural or choices
        boundary = min(pool, key=lambda value: (distances[value], value))
        selected.append(boundary)
        previous_position = bisect_left(boundaries, boundary)

    return tuple(selected)


def _lines_at(clusters: tuple[str, ...], boundaries: tuple[int, ...]) -> TextLines:
    edges = (0, *boundaries, len(clusters))
    return tuple("".join(clusters[start:end]) for start, end in pairwise(edges))


def horizontal_line_candidates(
    text: str,
    *,
    maximum_lines: int = MAXIMUM_AUTO_LINES,
) -> tuple[TextLines, ...]:
    """Return bounded, balanced candidates while preserving text and cluster boundaries."""
    if not isinstance(text, str) or not text:
        raise ValueError("text must be a non-empty string")
    if isinstance(maximum_lines, bool) or not isinstance(maximum_lines, int) or maximum_lines < 1:
        raise ValueError("maximum_lines must be a positive integer")

    clusters = _text_clusters(text)
    candidates: list[TextLines] = [(text,)]
    boundaries = tuple(
        index for index in range(1, len(clusters)) if _safe_boundary(clusters, index)
    )
    maximum = min(maximum_lines, len(boundaries) + 1)

    for line_count in range(2, maximum + 1):
        selected = _balanced_boundaries(clusters, boundaries, line_count)
        lines = _lines_at(clusters, selected)
        if any(not line or line.isspace() for line in lines):
            continue
        if lines not in candidates:
            candidates.append(lines)

    return tuple(candidates)
