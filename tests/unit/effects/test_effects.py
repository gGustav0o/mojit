from __future__ import annotations

import random
from collections.abc import Callable

import numpy as np
import pytest

from mojit.core.models import Frame, RenderContext, TextMask, Viewport
from mojit.effects.api import Effect, EffectConfig
from mojit.effects.chromatic import render_chromatic
from mojit.effects.glitch import render_glitch
from mojit.effects.neon import render_neon
from mojit.effects.pulse import render_pulse

EFFECTS: tuple[Effect, ...] = (
    render_neon,
    render_pulse,
    render_chromatic,
    render_glitch,
)
CONTINUOUS_EFFECTS: tuple[Effect, ...] = (render_neon, render_pulse, render_chromatic)


def _mask(width: int = 64, height: int = 48) -> TextMask:
    alpha = np.zeros((height, width), dtype=np.uint8)
    alpha[height // 4 : 3 * height // 4, width // 4 : 3 * width // 4] = 255
    alpha[height // 3 : 2 * height // 3, width // 3 : 2 * width // 3] = 128
    return TextMask(width, height, alpha)


def _context(mask: TextMask, frame_index: int = 0, elapsed: float = 0.0) -> RenderContext:
    return RenderContext(Viewport(mask.width, mask.height), frame_index, elapsed)


@pytest.mark.parametrize("renderer", EFFECTS)
def test_effects_return_deterministic_immutable_full_viewport_frames(renderer: Effect) -> None:
    mask = _mask()
    before = mask.alpha.tobytes()
    context = _context(mask, 17, 17 / 30)
    config = EffectConfig(42)

    first = renderer(mask, context, config)
    second = renderer(mask, context, config)

    assert isinstance(first, Frame)
    assert first == second
    assert first.rgba.shape == (mask.height, mask.width, 4)
    assert first.rgba.dtype == np.uint8
    assert not first.rgba.flags.writeable
    assert mask.alpha.tobytes() == before


@pytest.mark.parametrize("renderer", EFFECTS)
def test_effects_keep_empty_mask_fully_transparent(renderer: Effect) -> None:
    mask = TextMask(31, 25, np.zeros((25, 31), dtype=np.uint8))
    frame = renderer(mask, _context(mask, 5, 0.5), EffectConfig(-(2**63)))
    assert np.count_nonzero(frame.rgba) == 0


@pytest.mark.parametrize("renderer", CONTINUOUS_EFFECTS)
def test_non_stochastic_effects_do_not_depend_on_seed(renderer: Effect) -> None:
    mask = _mask()
    context = _context(mask, 9, 0.375)
    assert renderer(mask, context, EffectConfig(0)) == renderer(
        mask, context, EffectConfig(2**63 - 1)
    )


@pytest.mark.parametrize(
    ("renderer", "later"),
    [
        (render_neon, 0.25),
        (render_pulse, 0.25),
        (render_chromatic, 0.25),
    ],
)
def test_continuous_effects_change_with_elapsed_time(
    renderer: Callable[[TextMask, RenderContext, EffectConfig], Frame], later: float
) -> None:
    mask = _mask()
    initial = renderer(mask, _context(mask, 0, 0.0), EffectConfig(0))
    changed = renderer(mask, _context(mask, 1, later), EffectConfig(0))
    assert initial != changed


def test_glitch_changes_with_seed_and_frame_index() -> None:
    mask = _mask()
    baseline = render_glitch(mask, _context(mask, 0, 0.0), EffectConfig(0))
    other_seed = render_glitch(mask, _context(mask, 0, 0.0), EffectConfig(1))
    other_frame = render_glitch(mask, _context(mask, 1, 0.0), EffectConfig(0))
    assert baseline != other_seed
    assert baseline != other_frame


def test_glitch_does_not_touch_global_random_state() -> None:
    mask = _mask()
    python_before = random.getstate()
    numpy_before = np.random.get_state()

    render_glitch(mask, _context(mask, 23, 23 / 30), EffectConfig(-42))

    assert random.getstate() == python_before
    numpy_after = np.random.get_state()
    assert numpy_after[0] == numpy_before[0]
    assert np.array_equal(numpy_after[1], numpy_before[1])
    assert numpy_after[2:] == numpy_before[2:]
