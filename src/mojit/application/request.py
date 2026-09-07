"""Immutable application request assembled before terminal access."""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field

from mojit.core.models import MAX_SCENE_LAYERS, Orientation
from mojit.core.timing import MAX_FPS, MIN_FPS

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_EFFECT_ID = re.compile(r"[a-z][a-z0-9_-]*\Z")
_MAX_TEXT_CODEPOINTS = 4096


@dataclass(frozen=True, slots=True)
class PreparedRun:
    """Validated runtime values independent of CLI, files, and adapters."""

    text: str
    effect_id: str
    orientation: Orientation
    font_data: bytes = field(repr=False)
    font_fingerprint: str
    fps: int
    margin: float
    seed: int
    debug: bool = False
    scene_id: str | None = None
    scene_layers: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text or self.text.isspace():
            raise ValueError("text must contain at least one visible character")
        if "\0" in self.text or "\r" in self.text or "\n" in self.text:
            raise ValueError("text must be one NUL-free line")
        if len(self.text) > _MAX_TEXT_CODEPOINTS:
            raise ValueError("text must not exceed 4096 code points")
        if not isinstance(self.effect_id, str) or _EFFECT_ID.fullmatch(self.effect_id) is None:
            raise ValueError("effect_id must be a valid effect identifier")
        if not isinstance(self.orientation, Orientation):
            raise TypeError("orientation must be an Orientation")
        if not isinstance(self.font_data, bytes) or not self.font_data:
            raise ValueError("font_data must be non-empty bytes")
        if (
            not isinstance(self.font_fingerprint, str)
            or _SHA256.fullmatch(self.font_fingerprint) is None
        ):
            raise ValueError("font_fingerprint must be a lowercase SHA-256 digest")
        if hashlib.sha256(self.font_data).hexdigest() != self.font_fingerprint:
            raise ValueError("font_data does not match font_fingerprint")
        if (
            isinstance(self.fps, bool)
            or not isinstance(self.fps, int)
            or not MIN_FPS <= self.fps <= MAX_FPS
        ):
            raise ValueError(f"fps must be an integer between {MIN_FPS} and {MAX_FPS}")
        if isinstance(self.margin, bool) or not isinstance(self.margin, (int, float)):
            raise TypeError("margin must be a number")
        margin = float(self.margin)
        if not math.isfinite(margin) or not 0.0 <= margin < 0.5:
            raise ValueError("margin must be finite and satisfy 0 <= margin < 0.5")
        object.__setattr__(self, "margin", margin)
        if (
            isinstance(self.seed, bool)
            or not isinstance(self.seed, int)
            or not -(2**63) <= self.seed <= 2**63 - 1
        ):
            raise ValueError("seed must be a signed 64-bit integer")
        if not isinstance(self.debug, bool):
            raise TypeError("debug must be a boolean")
        if self.scene_id is not None and (
            not isinstance(self.scene_id, str) or _EFFECT_ID.fullmatch(self.scene_id) is None
        ):
            raise ValueError("scene_id must be a valid scene identifier")
        if self.scene_layers is not None:
            if not isinstance(self.scene_layers, tuple) or not self.scene_layers:
                raise ValueError("scene_layers must be a non-empty tuple")
            if len(self.scene_layers) > MAX_SCENE_LAYERS:
                raise ValueError(f"scene_layers must not exceed {MAX_SCENE_LAYERS} entries")
            if any(layer not in {"rain", "snow", "stars", "text"} for layer in self.scene_layers):
                raise ValueError("scene_layers contains an unknown layer")
            if self.scene_layers.count("text") != 1:
                raise ValueError("scene_layers must contain exactly one text layer")
        if self.scene_id is not None and self.scene_layers is not None:
            raise ValueError("scene_id and scene_layers are mutually exclusive")
