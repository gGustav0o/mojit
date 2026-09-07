"""Stateless deterministic rain streak layer."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageDraw

from mojit.core.compositor import RgbaColor
from mojit.core.models import Frame, RenderContext
from mojit.core.randomness import make_rng
from mojit.layers.api import (
    particle_count,
    periodic_distance,
    transparent_rgba,
    validate_color,
    validate_context,
    validate_int,
    validate_real,
    validate_seed,
)

_RNG_ID = "layer-rain-v1"


@dataclass(frozen=True, slots=True)
class RainLayer:
    """Blue slanted rain driven only by seed, viewport, and elapsed time."""

    seed: int
    density: float = 0.00018
    speed_px_per_second: float = 180.0
    streak_length_px: int = 14
    slant_px: int = -3
    color: RgbaColor = field(default_factory=lambda: RgbaColor(88, 174, 255, 150))
    streak_width_px: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "seed", validate_seed(self.seed))
        object.__setattr__(
            self,
            "density",
            validate_real(self.density, name="density", maximum=0.1),
        )
        object.__setattr__(
            self,
            "speed_px_per_second",
            validate_real(self.speed_px_per_second, name="speed_px_per_second"),
        )
        object.__setattr__(
            self,
            "streak_length_px",
            validate_int(self.streak_length_px, name="streak_length_px", minimum=1, maximum=256),
        )
        object.__setattr__(
            self,
            "streak_width_px",
            validate_int(self.streak_width_px, name="streak_width_px", minimum=1, maximum=32),
        )
        object.__setattr__(
            self,
            "slant_px",
            validate_int(self.slant_px, name="slant_px", minimum=-256, maximum=256),
        )
        object.__setattr__(self, "color", validate_color(self.color))

    def render(self, context: RenderContext) -> Frame:
        """Render clipped falling streaks without retaining particle history."""
        frame_context = validate_context(context)
        viewport = frame_context.viewport
        rgba = transparent_rgba(viewport)
        count = particle_count(viewport, self.density)
        if count == 0:
            return Frame(viewport.width_px, viewport.height_px, rgba)

        rng = make_rng(self.seed, _RNG_ID, 0)
        x_values = rng.uniform(-abs(self.slant_px), viewport.width_px + abs(self.slant_px), count)
        y_origins = rng.uniform(-self.streak_length_px, viewport.height_px, count)
        speed_factors = rng.uniform(0.72, 1.28, count)
        opacity_factors = rng.uniform(0.55, 1.0, count)
        cycle = viewport.height_px + self.streak_length_px * 2

        image = Image.fromarray(rgba, mode="RGBA")
        draw = ImageDraw.Draw(image)
        for x, origin_y, speed_factor, opacity_factor in zip(
            x_values,
            y_origins,
            speed_factors,
            opacity_factors,
            strict=True,
        ):
            distance = periodic_distance(
                frame_context.elapsed_seconds,
                self.speed_px_per_second,
                cycle,
                rate_factor=float(speed_factor),
            )
            y = (origin_y + distance + self.streak_length_px) % cycle - self.streak_length_px
            alpha = round(self.color.alpha * opacity_factor)
            draw.line(
                (
                    round(float(x)),
                    round(float(y)),
                    round(float(x)) + self.slant_px,
                    round(float(y)) + self.streak_length_px,
                ),
                fill=(self.color.red, self.color.green, self.color.blue, alpha),
                width=self.streak_width_px,
            )

        return Frame(
            viewport.width_px,
            viewport.height_px,
            np.asarray(image, dtype=np.uint8),
        )
