from __future__ import annotations

import pytest

from mojit.config.models import ConfigOverrides, ConfigValidationError
from mojit.config.toml import ConfigSyntaxError, parse_toml_config
from mojit.core.models import Orientation


def test_parse_complete_document() -> None:
    parsed = parse_toml_config(
        'effect = "glitch"\norientation = "vertical"\nfont = "font.ttf"\n'
        "fps = 60\nmargin = 0.1\nseed = 0\n"
    )

    assert parsed == ConfigOverrides(
        effect="glitch",
        orientation=Orientation.VERTICAL,
        font="font.ttf",
        fps=60,
        margin=0.1,
        seed=0,
    )


def test_parse_accepts_utf8_bytes() -> None:
    assert parse_toml_config(b'effect = "neon"\n').effect == "neon"


@pytest.mark.parametrize("document", [b"\xff", "effect = [", 'effect = "unterminated'])
def test_parse_maps_syntax_and_encoding_errors(document: str | bytes) -> None:
    with pytest.raises(ConfigSyntaxError):
        parse_toml_config(document)


@pytest.mark.parametrize("document", ["unknown = 1", "[render]\nfps = 30", "debug = true"])
def test_parse_rejects_unknown_and_nested_keys(document: str) -> None:
    with pytest.raises(ConfigValidationError, match="unknown"):
        parse_toml_config(document)


@pytest.mark.parametrize(
    "document",
    [
        "fps = true",
        'fps = "30"',
        "seed = 1.0",
        "margin = true",
        "font = 42",
        'orientation = "diagonal"',
        'effect = ""',
    ],
)
def test_parse_rejects_wrong_exact_types_and_values(document: str) -> None:
    with pytest.raises(ConfigValidationError):
        parse_toml_config(document)


def test_parse_rejects_non_document_input() -> None:
    with pytest.raises(TypeError):
        parse_toml_config(1)  # type: ignore[arg-type]
