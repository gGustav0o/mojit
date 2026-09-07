"""Pure Unicode-aware candidates for automatic horizontal line breaking."""

from __future__ import annotations

import unicodedata
from itertools import pairwise

TextLines = tuple[str, ...]
TextPhrases = tuple[str, ...]

MAXIMUM_AUTO_LINES = 16
MINIMUM_AUTO_LINE_WEIGHT = 4

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


def _text_weight(text: str) -> int:
    return sum(map(_cluster_weight, _text_clusters(text)))


def validate_text_phrases(text: str, phrases: TextPhrases) -> None:
    """Require an immutable, lossless partition of one non-empty source string."""
    if not isinstance(text, str) or not text:
        raise ValueError("text must be a non-empty string")
    if not isinstance(phrases, tuple):
        raise TypeError("phrases must be an immutable tuple")
    if not phrases or any(not isinstance(phrase, str) or not phrase for phrase in phrases):
        raise ValueError("phrases must contain non-empty strings")
    if "".join(phrases) != text:
        raise ValueError("phrases must reproduce text exactly")


def _phrase_boundaries(
    phrases: TextPhrases,
    clusters: tuple[str, ...],
) -> tuple[int, ...]:
    offsets_to_clusters: dict[int, int] = {}
    offset = 0
    for index, cluster in enumerate(clusters, start=1):
        offset += len(cluster)
        offsets_to_clusters[offset] = index

    boundaries: list[int] = []
    phrase_offset = 0
    for phrase in phrases[:-1]:
        phrase_offset += len(phrase)
        cluster_index = offsets_to_clusters.get(phrase_offset)
        if cluster_index is not None and _safe_boundary(clusters, cluster_index):
            boundaries.append(cluster_index)
    return tuple(boundaries)


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
        boundary = min(choices, key=lambda value: (distances[value], value))
        selected.append(boundary)
        previous_position = boundaries.index(boundary, first_position, last_position + 1)

    return tuple(selected)


def _lines_at(clusters: tuple[str, ...], boundaries: tuple[int, ...]) -> TextLines:
    edges = (0, *boundaries, len(clusters))
    return tuple("".join(clusters[start:end]) for start, end in pairwise(edges))


def horizontal_line_candidates(
    text: str,
    *,
    phrases: TextPhrases,
    maximum_lines: int = MAXIMUM_AUTO_LINES,
) -> tuple[TextLines, ...]:
    """Balance only language-approved, Unicode-safe phrase boundaries."""
    validate_text_phrases(text, phrases)
    if isinstance(maximum_lines, bool) or not isinstance(maximum_lines, int) or maximum_lines < 1:
        raise ValueError("maximum_lines must be a positive integer")

    clusters = _text_clusters(text)
    candidates: list[TextLines] = [(text,)]
    boundaries = _phrase_boundaries(phrases, clusters)
    maximum = min(maximum_lines, len(boundaries) + 1)

    for line_count in range(2, maximum + 1):
        selected = _balanced_boundaries(clusters, boundaries, line_count)
        lines = _lines_at(clusters, selected)
        if any(
            not line or line.isspace() or _text_weight(line) < MINIMUM_AUTO_LINE_WEIGHT
            for line in lines
        ):
            continue
        if lines not in candidates:
            candidates.append(lines)

    return tuple(candidates)
