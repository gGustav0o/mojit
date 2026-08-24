from __future__ import annotations

from pathlib import Path

import pytest

from mojit.config.models import (
    DEFAULT_EFFECT,
    DEFAULT_FONT,
    DEFAULT_FPS,
    DEFAULT_MARGIN,
    DEFAULT_ORIENTATION,
    DEFAULT_SEED,
    ConfigOverrides,
    ConfigValidationError,
)
from mojit.config.resolve import resolve_config
from mojit.core.models import Orientation

CWD = Path("C:/work")
CONFIG_DIR = Path("C:/settings")


def test_resolution_uses_defaults() -> None:
    result = resolve_config(ConfigOverrides(), ConfigOverrides(), cwd=CWD, config_dir=None)

    assert (result.effect, result.orientation, result.font) == (
        DEFAULT_EFFECT,
        DEFAULT_ORIENTATION,
        DEFAULT_FONT,
    )
    assert (result.fps, result.margin, result.seed, result.debug) == (
        DEFAULT_FPS,
        DEFAULT_MARGIN,
        DEFAULT_SEED,
        False,
    )


@pytest.mark.parametrize(
    ("field", "file_value", "cli_value"),
    [
        ("effect", "pulse", "glitch"),
        ("orientation", Orientation.VERTICAL, Orientation.HORIZONTAL),
        ("font", "file.ttf", "cli.ttf"),
        ("fps", 10, 15),
        ("margin", 0.0, 0.2),
        ("seed", 42, 0),
    ],
)
def test_cli_precedes_file_for_every_field(
    field: str, file_value: object, cli_value: object
) -> None:
    result = resolve_config(
        ConfigOverrides(**{field: cli_value}),
        ConfigOverrides(**{field: file_value}),
        cwd=CWD,
        config_dir=CONFIG_DIR,
    )
    expected = CWD / "cli.ttf" if field == "font" else cli_value
    assert getattr(result, field) == expected


def test_file_values_precede_defaults_and_font_uses_config_directory() -> None:
    result = resolve_config(
        ConfigOverrides(),
        ConfigOverrides(
            effect="pulse",
            orientation=Orientation.VERTICAL,
            font="fonts/cjk.ttf",
            fps=1,
            margin=0.0,
            seed=0,
        ),
        cwd=CWD,
        config_dir=CONFIG_DIR,
        debug=True,
    )

    assert result.font == CONFIG_DIR / "fonts" / "cjk.ttf"
    assert result.seed == 0
    assert result.debug is True


def test_config_font_requires_its_source_directory() -> None:
    with pytest.raises(ConfigValidationError, match="config_dir"):
        resolve_config(
            ConfigOverrides(), ConfigOverrides(font="font.ttf"), cwd=CWD, config_dir=None
        )


def test_resolution_requires_absolute_context_paths() -> None:
    with pytest.raises(ConfigValidationError, match="cwd"):
        resolve_config(ConfigOverrides(), ConfigOverrides(), cwd=Path("relative"), config_dir=None)
