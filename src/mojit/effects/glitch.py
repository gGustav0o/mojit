"""Deterministic stochastic band-displacement effect."""

from __future__ import annotations

from mojit.core.compositor import (
    HorizontalBandShift,
    merge_color_channels,
    translate_mask,
    warp_horizontal_bands,
)
from mojit.core.models import Frame, RenderContext, TextMask
from mojit.core.randomness import make_rng
from mojit.effects.api import EffectConfig, validate_effect_inputs

_EFFECT_ID = "glitch"


def _band_shifts(
    mask: TextMask, context: RenderContext, config: EffectConfig
) -> tuple[HorizontalBandShift, ...]:
    rng = make_rng(config.seed, _EFFECT_ID, context.frame_index)
    count = max(1, min(12, mask.height // 24))
    maximum_shift = max(1, mask.width // 18)
    shifts: list[HorizontalBandShift] = []
    for index in range(count):
        cell_top = index * mask.height // count
        cell_bottom = (index + 1) * mask.height // count
        cell_height = cell_bottom - cell_top
        maximum_height = max(1, cell_height // 2)
        band_height = int(rng.integers(1, maximum_height + 1))
        room = cell_height - band_height
        top = cell_top + int(rng.integers(0, room + 1))
        shift = int(rng.integers(-maximum_shift, maximum_shift + 1))
        if shift == 0:
            shift = 1 if index % 2 == 0 else -1
        shifts.append(HorizontalBandShift(top, top + band_height, shift))
    return tuple(shifts)


def render_glitch(mask: TextMask, context: RenderContext, config: EffectConfig) -> Frame:
    """Render reproducible band tearing and bounded channel separation."""
    source, render_context, effect_config = validate_effect_inputs(mask, context, config)
    warped = warp_horizontal_bands(source, _band_shifts(source, render_context, effect_config))
    separation = max(1, min(4, source.width // 160 + 1))
    if (effect_config.seed + render_context.frame_index) & 1:
        separation = -separation
    red = translate_mask(warped, -separation, 0)
    blue = translate_mask(warped, separation, 0)
    return merge_color_channels(red, warped, blue)
