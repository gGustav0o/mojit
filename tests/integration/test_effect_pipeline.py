from __future__ import annotations

import numpy as np
import pytest

from mojit.core.models import RenderContext, TextMask, Viewport
from mojit.effects.api import EffectConfig
from mojit.effects.registry import effect_names, get_effect


def _synthetic_mask(width: int, height: int, *, edge: bool) -> TextMask:
    alpha = np.zeros((height, width), dtype=np.uint8)
    if edge:
        alpha[0 : max(1, height // 3), 0 : max(1, width // 3)] = 255
        alpha[-1, :] = 96
    else:
        alpha[height // 4 : 3 * height // 4, width // 4 : 3 * width // 4] = 220
    return TextMask(width, height, alpha)


@pytest.mark.parametrize(("width", "height"), [(32, 24), (31, 25)])
@pytest.mark.parametrize("edge", [False, True])
@pytest.mark.parametrize("seed", [-(2**63), 2**63 - 1])
def test_registry_pipeline_renders_all_effects_in_memory(
    width: int, height: int, edge: bool, seed: int
) -> None:
    mask = _synthetic_mask(width, height, edge=edge)
    context = RenderContext(Viewport(width, height), frame_index=13, elapsed_seconds=13 / 30)

    for effect_id in effect_names():
        renderer = get_effect(effect_id)
        first = renderer(mask, context, EffectConfig(seed))
        second = renderer(mask, context, EffectConfig(seed))
        assert first == second
        assert (first.width, first.height) == (width, height)
        assert first.rgba.dtype == np.uint8
        assert not first.rgba.flags.writeable
