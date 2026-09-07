"""Stateless deterministic twinkling star layer."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageDraw

from mojit.core.compositor import RgbaColor
from mojit.core.models import Frame, RenderContext
from mojit.core.randomness import make_rng
from mojit.layers.api import (
    particle_count,
    transparent_rgba,
    validate_color,
    validate_context,
    validate_int,
    validate_real,
    validate_seed,
)

_RNG_ID = "layer-stars-v1"


@dataclass(frozen=True, slots=True)
class StarsLayer:
    """A fixed seeded star field with continuous deterministic twinkle."""

    seed: int
    density: float = 0.00012
    twinkle_hz: float = 0.7
    radius_px: int = 1
    color: RgbaColor = field(default_factory=lambda: RgbaColor(222, 235, 255, 220))

    def __post_init__(self) -> None:
        object.__setattr__(self, "seed", validate_seed(self.seed))
        object.__setattr__(
            self,
            "density",
            validate_real(self.density, name="density", maximum=0.1),
        )
        object.__setattr__(
            self,
            "twinkle_hz",
            validate_real(self.twinkle_hz, name="twinkle_hz", maximum=20.0),
        )
        object.__setattr__(
            self,
            "radius_px",
            validate_int(self.radius_px, name="radius_px", minimum=1, maximum=8),
        )
        object.__setattr__(self, "color", validate_color(self.color))

    def render(self, context: RenderContext) -> Frame:
        """Render the field from scratch for the supplied deterministic time."""
        frame_context = validate_context(context)
        viewport = frame_context.viewport
        rgba = transparent_rgba(viewport)
        count = particle_count(viewport, self.density)
        if count == 0:
            return Frame(viewport.width_px, viewport.height_px, rgba)

        rng = make_rng(self.seed, _RNG_ID, 0)
        x_values = rng.integers(0, viewport.width_px, count)
        y_values = rng.integers(0, viewport.height_px, count)
        phases = rng.uniform(0.0, math.tau, count)
        strengths = rng.uniform(0.55, 1.0, count)

        image = Image.fromarray(rgba, mode="RGBA")
        draw = ImageDraw.Draw(image)
        for x, y, phase, strength in zip(
            x_values,
            y_values,
            phases,
            strengths,
            strict=True,
        ):
            wave = 0.5 + 0.5 * math.sin(
                float(phase) + math.tau * self.twinkle_hz * frame_context.elapsed_seconds
            )
            alpha = round(self.color.alpha * float(strength) * (0.3 + 0.7 * wave))
            center_x = int(x)
            center_y = int(y)
            radius = self.radius_px - 1
            if radius == 0:
                draw.point(
                    (center_x, center_y),
                    fill=(self.color.red, self.color.green, self.color.blue, alpha),
                )
                continue
            draw.ellipse(
                (
                    center_x - radius,
                    center_y - radius,
                    center_x + radius,
                    center_y + radius,
                ),
                fill=(self.color.red, self.color.green, self.color.blue, alpha),
            )

        return Frame(
            viewport.width_px,
            viewport.height_px,
            np.asarray(image, dtype=np.uint8),
        )
