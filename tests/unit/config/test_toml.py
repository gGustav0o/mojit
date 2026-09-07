from __future__ import annotations

import pytest

from mojit.config.models import ConfigOverrides, ConfigValidationError
from mojit.config.toml import ConfigSyntaxError, parse_toml_config
from mojit.core.models import MAX_SCENE_LAYERS, Orientation


def test_parse_complete_document() -> None:
    parsed = parse_toml_config(
        'effect = "glitch"\norientation = "vertical"\nfont = "font.ttf"\n'
        "fps = 15\nmargin = 0.1\nseed = 0\n"
        'scene = "rainy-night"\n'
    )

    assert parsed == ConfigOverrides(
        effect="glitch",
        orientation=Orientation.VERTICAL,
        font="font.ttf",
        fps=15,
        margin=0.1,
        seed=0,
        scene="rainy-night",
    )


def test_parse_accepts_utf8_bytes() -> None:
    assert parse_toml_config(b'effect = "neon"\n').effect == "neon"


def test_parse_accepts_versioned_ordered_custom_scene_layers() -> None:
    parsed = parse_toml_config('scene_version = 1\nlayers = ["stars", "rain", "text"]\n')
    assert parsed.scene is None
    assert parsed.scene_layers == ("stars", "rain", "text")


@pytest.mark.parametrize("document", [b"\xff", "effect = [", 'effect = "unterminated'])
def test_parse_maps_syntax_and_encoding_errors(document: str | bytes) -> None:
    with pytest.raises(ConfigSyntaxError):
        parse_toml_config(document)


@pytest.mark.parametrize("document", ["unknown = 1", "[render]\nfps = 8", "debug = true"])
def test_parse_rejects_unknown_and_nested_keys(document: str) -> None:
    with pytest.raises(ConfigValidationError, match="unknown"):
        parse_toml_config(document)


@pytest.mark.parametrize(
    "document",
    [
        "fps = true",
        'fps = "8"',
        "seed = 1.0",
        "margin = true",
        "font = 42",
        'orientation = "diagonal"',
        'effect = ""',
        'scene_version = 2\nlayers = ["text"]',
        "scene_version = 1",
        'layers = ["text"]',
        'scene_version = 1\nlayers = ["unknown", "text"]',
        'scene_version = 1\nlayers = ["stars"]',
        'scene_version = 1\nlayers = ["text", "text"]',
        'scene = "space"\nscene_version = 1\nlayers = ["text"]',
    ],
)
def test_parse_rejects_wrong_exact_types_and_values(document: str) -> None:
    with pytest.raises(ConfigValidationError):
        parse_toml_config(document)


def test_parse_rejects_non_document_input() -> None:
    with pytest.raises(TypeError):
        parse_toml_config(1)  # type: ignore[arg-type]


def test_parse_rejects_a_custom_scene_above_the_layer_limit() -> None:
    layers = ", ".join(['"stars"'] * MAX_SCENE_LAYERS + ['"text"'])

    with pytest.raises(ConfigValidationError, match=str(MAX_SCENE_LAYERS)):
        parse_toml_config(f"scene_version = 1\nlayers = [{layers}]\n")
