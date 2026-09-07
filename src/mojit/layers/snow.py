"""Stateless deterministic drifting snow layer."""

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
    periodic_distance,
    periodic_phase,
    transparent_rgba,
    validate_color,
    validate_context,
    validate_int,
    validate_real,
    validate_seed,
)

_RNG_ID = "layer-snow-v1"


@dataclass(frozen=True, slots=True)
class SnowLayer:
    """Soft falling flakes with seeded speeds, sizes, and horizontal drift."""

    seed: int
    density: float = 0.0001
    speed_px_per_second: float = 28.0
    drift_px: float = 12.0
    drift_hz: float = 0.08
    max_radius_px: int = 2
    color: RgbaColor = field(default_factory=lambda: RgbaColor(244, 248, 255, 205))

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
            "drift_px",
            validate_real(self.drift_px, name="drift_px", maximum=4096.0),
        )
        object.__setattr__(
            self,
            "drift_hz",
            validate_real(self.drift_hz, name="drift_hz", maximum=20.0),
        )
        object.__setattr__(
            self,
            "max_radius_px",
            validate_int(self.max_radius_px, name="max_radius_px", minimum=1, maximum=16),
        )
        object.__setattr__(self, "color", validate_color(self.color))

    def render(self, context: RenderContext) -> Frame:
        """Render bounded flakes without carrying state across frames or resizes."""
        frame_context = validate_context(context)
        viewport = frame_context.viewport
        rgba = transparent_rgba(viewport)
        count = particle_count(viewport, self.density)
        if count == 0:
            return Frame(viewport.width_px, viewport.height_px, rgba)

        rng = make_rng(self.seed, _RNG_ID, 0)
        x_origins = rng.uniform(0.0, viewport.width_px, count)
        y_origins = rng.uniform(-self.max_radius_px, viewport.height_px, count)
        phases = rng.uniform(0.0, math.tau, count)
        speed_factors = rng.uniform(0.55, 1.25, count)
        radii = rng.integers(1, self.max_radius_px + 1, count)
        opacity_factors = rng.uniform(0.65, 1.0, count)

        image = Image.fromarray(rgba, mode="RGBA")
        draw = ImageDraw.Draw(image)
        for origin_x, origin_y, phase, speed_factor, radius, opacity_factor in zip(
            x_origins,
            y_origins,
            phases,
            speed_factors,
            radii,
            opacity_factors,
            strict=True,
        ):
            radius_px = int(radius)
            cycle = viewport.height_px + radius_px * 2
            distance = periodic_distance(
                frame_context.elapsed_seconds,
                self.speed_px_per_second,
                cycle,
                rate_factor=float(speed_factor),
            )
            y = (origin_y + distance + radius_px) % cycle - radius_px
            x = (
                origin_x
                + math.sin(
                    float(phase) + periodic_phase(frame_context.elapsed_seconds, self.drift_hz)
                )
                * self.drift_px
            ) % viewport.width_px
            alpha = round(self.color.alpha * float(opacity_factor))
            center_x = round(float(x))
            center_y = round(float(y))
            draw.ellipse(
                (
                    center_x - radius_px,
                    center_y - radius_px,
                    center_x + radius_px,
                    center_y + radius_px,
                ),
                fill=(self.color.red, self.color.green, self.color.blue, alpha),
            )

        return Frame(
            viewport.width_px,
            viewport.height_px,
            np.asarray(image, dtype=np.uint8),
        )
