"""Deterministic breathing neon effect."""

from __future__ import annotations

import math

from mojit.core.compositor import RgbaColor, blur_mask, composite_colorized_masks
from mojit.core.models import Frame, RenderContext, TextMask
from mojit.effects.api import EffectConfig, validate_effect_inputs

_OUTER_RGB = (0, 82, 255)
_INNER = RgbaColor(0, 224, 255, 176)
_CORE = RgbaColor(222, 255, 255)


def render_neon(mask: TextMask, context: RenderContext, config: EffectConfig) -> Frame:
    """Render cyan layers with a slow deterministic glow pulse."""
    source, render_context, _ = validate_effect_inputs(mask, context, config)
    short_side = min(source.width, source.height)
    phase = 0.5 + 0.5 * math.sin(math.tau * 0.65 * render_context.elapsed_seconds)
    inner_radius = max(1.0, short_side * 0.006)
    outer_radius = max(inner_radius + 1.0, short_side * (0.018 + 0.006 * phase))
    outer_alpha = round(72 + 48 * phase)

    return composite_colorized_masks(
        (
            (blur_mask(source, outer_radius), RgbaColor(*_OUTER_RGB, outer_alpha)),
            (blur_mask(source, inner_radius), _INNER),
            (source, _CORE),
        )
    )
