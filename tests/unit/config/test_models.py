from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from mojit.config.models import ConfigOverrides, ConfigValidationError, ResolvedConfig
from mojit.core.models import Orientation


@pytest.mark.parametrize("fps", [1, 30, 60])
def test_overrides_accept_fps_boundaries(fps: int) -> None:
    assert ConfigOverrides(fps=fps).fps == fps


@pytest.mark.parametrize("fps", [0, 61, True, 1.5])
def test_overrides_reject_invalid_fps(fps: object) -> None:
    with pytest.raises(ConfigValidationError):
        ConfigOverrides(fps=fps)  # type: ignore[arg-type]


@pytest.mark.parametrize("margin", [0, 0.08, 0.499999])
def test_overrides_accept_margin_boundaries(margin: float) -> None:
    assert ConfigOverrides(margin=margin).margin == float(margin)


@pytest.mark.parametrize("margin", [-0.01, 0.5, float("inf"), float("nan"), True])
def test_overrides_reject_invalid_margin(margin: object) -> None:
    with pytest.raises(ConfigValidationError):
        ConfigOverrides(margin=margin)  # type: ignore[arg-type]


@pytest.mark.parametrize("seed", [-(2**63), 0, 2**63 - 1])
def test_overrides_accept_seed_boundaries(seed: int) -> None:
    assert ConfigOverrides(seed=seed).seed == seed


@pytest.mark.parametrize("seed", [-(2**63) - 1, 2**63, True, 1.5])
def test_overrides_reject_invalid_seed(seed: object) -> None:
    with pytest.raises(ConfigValidationError):
        ConfigOverrides(seed=seed)  # type: ignore[arg-type]


@pytest.mark.parametrize("effect", ["neon", "x", "glitch_2", "chromatic-shift"])
def test_overrides_accept_effect_identifiers(effect: str) -> None:
    assert ConfigOverrides(effect=effect).effect == effect


@pytest.mark.parametrize("effect", ["", "Neon", "2neon", "neon glow", 1])
def test_overrides_reject_invalid_effect_identifiers(effect: object) -> None:
    with pytest.raises(ConfigValidationError):
        ConfigOverrides(effect=effect)  # type: ignore[arg-type]


@pytest.mark.parametrize("font", ["", "   ", 1])
def test_overrides_reject_invalid_font_paths(font: object) -> None:
    with pytest.raises(ConfigValidationError):
        ConfigOverrides(font=font)  # type: ignore[arg-type]


def test_models_are_frozen_and_resolved_state_is_complete() -> None:
    resolved = ResolvedConfig(
        effect="neon",
        orientation=Orientation.HORIZONTAL,
        font=Path("C:/font.ttf"),
        fps=30,
        margin=0.08,
        seed=0,
    )

    with pytest.raises(FrozenInstanceError):
        resolved.fps = 60  # type: ignore[misc]


def test_resolved_config_requires_absolute_font_and_boolean_debug() -> None:
    values = {
        "effect": "neon",
        "orientation": Orientation.HORIZONTAL,
        "fps": 30,
        "margin": 0.08,
        "seed": 0,
    }
    with pytest.raises(ConfigValidationError, match="absolute"):
        ResolvedConfig(font=Path("font.ttf"), **values)
    with pytest.raises(ConfigValidationError, match="debug"):
        ResolvedConfig(font=Path("C:/font.ttf"), debug=1, **values)  # type: ignore[arg-type]
