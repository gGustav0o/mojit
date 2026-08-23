"""Deterministic chromatic channel displacement effect."""

from __future__ import annotations

import math

from mojit.core.compositor import merge_color_channels, translate_mask
from mojit.core.models import Frame, RenderContext, TextMask
from mojit.effects.api import EffectConfig, validate_effect_inputs


def render_chromatic(mask: TextMask, context: RenderContext, config: EffectConfig) -> Frame:
    """Render oscillating symmetric red and blue channel offsets."""
    source, render_context, _ = validate_effect_inputs(mask, context, config)
    amplitude = max(1, round(source.width * 0.012))
    offset = round(amplitude * math.sin(math.tau * 0.7 * render_context.elapsed_seconds))
    red = translate_mask(source, -offset, 0)
    blue = translate_mask(source, offset, 0)
    return merge_color_channels(red, source, blue)
