"""Immutable configuration models and strict value validation."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

from mojit.core.models import MAX_SCENE_LAYERS, Orientation
from mojit.core.timing import MAX_FPS, MIN_FPS

DEFAULT_EFFECT = "neon"
DEFAULT_ORIENTATION = Orientation.HORIZONTAL
DEFAULT_FONT = Path("C:/Windows/Fonts/YuGothB.ttc")
DEFAULT_FPS = 8
DEFAULT_MARGIN = 0.08
DEFAULT_SEED = 0
DEFAULT_SCENE: str | None = None

MIN_SEED = -(2**63)
MAX_SEED = 2**63 - 1

_EFFECT_ID = re.compile(r"[a-z][a-z0-9_-]*\Z")
_SCENE_LAYER_IDS = frozenset({"rain", "snow", "stars", "text"})


class ConfigValidationError(ValueError):
    """A configuration value violates the public contract."""


def validate_effect(value: object) -> str:
    if not isinstance(value, str) or _EFFECT_ID.fullmatch(value) is None:
        raise ConfigValidationError("effect must match [a-z][a-z0-9_-]*")
    return value


def validate_scene(value: object) -> str:
    if not isinstance(value, str) or _EFFECT_ID.fullmatch(value) is None:
        raise ConfigValidationError("scene must match [a-z][a-z0-9_-]*")
    return value


def validate_scene_layers(value: object) -> tuple[str, ...]:
    if not isinstance(value, tuple) or not value:
        raise ConfigValidationError("scene layers must be a non-empty tuple")
    if len(value) > MAX_SCENE_LAYERS:
        raise ConfigValidationError(f"scene layers must not exceed {MAX_SCENE_LAYERS} entries")
    if any(type(layer) is not str or layer not in _SCENE_LAYER_IDS for layer in value):
        available = ", ".join(sorted(_SCENE_LAYER_IDS))
        raise ConfigValidationError(f"scene layers must be one of: {available}")
    if value.count("text") != 1:
        raise ConfigValidationError("scene layers must contain exactly one text layer")
    return value


def validate_orientation(value: object) -> Orientation:
    if not isinstance(value, Orientation):
        raise ConfigValidationError("orientation must be horizontal or vertical")
    return value


def validate_font(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigValidationError("font must be a non-empty path string")
    return value


def validate_fps(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigValidationError("fps must be an integer")
    if not MIN_FPS <= value <= MAX_FPS:
        raise ConfigValidationError(f"fps must be between {MIN_FPS} and {MAX_FPS}")
    return value


def validate_margin(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigValidationError("margin must be a number")
    converted = float(value)
    if not math.isfinite(converted) or not 0.0 <= converted < 0.5:
        raise ConfigValidationError("margin must be finite and satisfy 0 <= margin < 0.5")
    return converted


def validate_seed(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigValidationError("seed must be an integer")
    if not MIN_SEED <= value <= MAX_SEED:
        raise ConfigValidationError("seed must be a signed 64-bit integer")
    return value


@dataclass(frozen=True, slots=True)
class ConfigOverrides:
    """Values supplied by exactly one optional configuration source."""

    effect: str | None = None
    orientation: Orientation | None = None
    font: str | None = None
    fps: int | None = None
    margin: float | None = None
    seed: int | None = None
    scene: str | None = None
    scene_layers: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        if self.effect is not None:
            object.__setattr__(self, "effect", validate_effect(self.effect))
        if self.orientation is not None:
            object.__setattr__(self, "orientation", validate_orientation(self.orientation))
        if self.font is not None:
            object.__setattr__(self, "font", validate_font(self.font))
        if self.fps is not None:
            object.__setattr__(self, "fps", validate_fps(self.fps))
        if self.margin is not None:
            object.__setattr__(self, "margin", validate_margin(self.margin))
        if self.seed is not None:
            object.__setattr__(self, "seed", validate_seed(self.seed))
        if self.scene is not None:
            object.__setattr__(self, "scene", validate_scene(self.scene))
        if self.scene_layers is not None:
            object.__setattr__(self, "scene_layers", validate_scene_layers(self.scene_layers))
        if self.scene is not None and self.scene_layers is not None:
            raise ConfigValidationError("scene and custom scene layers are mutually exclusive")


@dataclass(frozen=True, slots=True)
class ResolvedConfig:
    """Complete validated configuration consumed by the composition root."""

    effect: str
    orientation: Orientation
    font: Path
    fps: int
    margin: float
    seed: int
    debug: bool = False
    scene: str | None = None
    scene_layers: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "effect", validate_effect(self.effect))
        object.__setattr__(self, "orientation", validate_orientation(self.orientation))
        if not isinstance(self.font, Path) or not self.font.is_absolute():
            raise ConfigValidationError("font must be an absolute Path")
        object.__setattr__(self, "fps", validate_fps(self.fps))
        object.__setattr__(self, "margin", validate_margin(self.margin))
        object.__setattr__(self, "seed", validate_seed(self.seed))
        if self.scene is not None:
            object.__setattr__(self, "scene", validate_scene(self.scene))
        if self.scene_layers is not None:
            object.__setattr__(self, "scene_layers", validate_scene_layers(self.scene_layers))
        if self.scene is not None and self.scene_layers is not None:
            raise ConfigValidationError("scene and custom scene layers are mutually exclusive")
        if not isinstance(self.debug, bool):
            raise ConfigValidationError("debug must be a boolean")
