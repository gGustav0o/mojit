"""Deterministic centered pulse effect."""

from __future__ import annotations

import math

from mojit.core.compositor import (
    RgbaColor,
    alpha_composite,
    blur_mask,
    colorize_mask,
    scale_mask_centered,
)
from mojit.core.models import Frame, RenderContext, TextMask
from mojit.effects.api import EffectConfig, validate_effect_inputs

_GLOW = RgbaColor(112, 24, 255, 112)
_CORE = RgbaColor(255, 72, 205)


def render_pulse(mask: TextMask, context: RenderContext, config: EffectConfig) -> Frame:
    """Render a smooth 0.93..1.0 centered scale cycle."""
    source, render_context, _ = validate_effect_inputs(mask, context, config)
    phase = 0.5 + 0.5 * math.sin(math.tau * 0.8 * render_context.elapsed_seconds)
    scaled = scale_mask_centered(source, 0.93 + 0.07 * phase)
    radius = max(1.0, min(source.width, source.height) * 0.006)
    glow = colorize_mask(blur_mask(scaled, radius), _GLOW)
    core = colorize_mask(scaled, _CORE)
    return alpha_composite(glow, core)
