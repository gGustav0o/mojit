from __future__ import annotations

import random
from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from mojit.core.models import Frame, RenderContext, Viewport
from mojit.layers.api import LayerInputError
from mojit.layers.rain import RainLayer
from mojit.layers.snow import SnowLayer
from mojit.layers.stars import StarsLayer


def _context(viewport: Viewport | None = None, *, elapsed: float = 1.25) -> RenderContext:
    return RenderContext(viewport or Viewport(96, 64), frame_index=10, elapsed_seconds=elapsed)


LAYERS = (
    RainLayer(11, density=0.004),
    StarsLayer(22, density=0.004),
    SnowLayer(33, density=0.004),
)


@pytest.mark.parametrize("layer", LAYERS)
def test_ambient_layers_are_deterministic_immutable_full_viewport_frames(layer: object) -> None:
    context = _context()
    first = layer.render(context)  # type: ignore[attr-defined]
    repeated = layer.render(context)  # type: ignore[attr-defined]

    assert isinstance(first, Frame)
    assert first == repeated
    assert first.rgba.shape == (64, 96, 4)
    assert np.count_nonzero(first.rgba[..., 3]) > 0
    assert not first.rgba.flags.writeable


@pytest.mark.parametrize("layer", LAYERS)
def test_ambient_layers_change_with_elapsed_time(layer: object) -> None:
    assert layer.render(_context(elapsed=0.0)) != layer.render(  # type: ignore[attr-defined]
        _context(elapsed=0.75)
    )


@pytest.mark.parametrize("layer", LAYERS)
def test_ambient_layers_recompute_after_resize_without_retained_history(layer: object) -> None:
    small_context = _context(Viewport(48, 32))
    first = layer.render(small_context)  # type: ignore[attr-defined]
    large = layer.render(_context(Viewport(120, 80)))  # type: ignore[attr-defined]
    repeated_small = layer.render(small_context)  # type: ignore[attr-defined]

    assert first == repeated_small
    assert (large.width, large.height) == (120, 80)


@pytest.mark.parametrize("layer", LAYERS)
def test_ambient_layers_do_not_touch_global_random_state(layer: object) -> None:
    python_before = random.getstate()
    numpy_before = np.random.get_state()

    layer.render(_context())  # type: ignore[attr-defined]

    assert random.getstate() == python_before
    numpy_after = np.random.get_state()
    assert numpy_after[0] == numpy_before[0]
    assert np.array_equal(numpy_after[1], numpy_before[1])
    assert numpy_after[2:] == numpy_before[2:]


def test_ambient_layer_outputs_are_visually_distinct() -> None:
    frames = [layer.render(_context()) for layer in LAYERS]
    assert frames[0] != frames[1]
    assert frames[0] != frames[2]
    assert frames[1] != frames[2]


def test_larger_star_radius_draws_a_visible_disc() -> None:
    frame = StarsLayer(7, density=0.004, radius_px=2).render(_context())
    assert np.count_nonzero(frame.rgba[..., 3]) > 0


def test_wider_rain_streaks_increase_visible_coverage() -> None:
    thin = RainLayer(7, density=0.004, streak_width_px=1).render(_context())
    wide = RainLayer(7, density=0.004, streak_width_px=3).render(_context())
    assert np.count_nonzero(wide.rgba[..., 3]) > np.count_nonzero(thin.rgba[..., 3])


@pytest.mark.parametrize(
    "layer",
    [RainLayer(0, density=0), StarsLayer(0, density=0), SnowLayer(0, density=0)],
)
def test_zero_density_returns_a_transparent_frame(layer: object) -> None:
    assert np.count_nonzero(layer.render(_context()).rgba) == 0  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "factory",
    [
        lambda: RainLayer(0, speed_px_per_second=-1),
        lambda: RainLayer(0, streak_length_px=0),
        lambda: RainLayer(0, streak_width_px=0),
        lambda: StarsLayer(0, density=0.2),
        lambda: StarsLayer(0, radius_px=0),
        lambda: SnowLayer(0, drift_px=-1),
        lambda: SnowLayer(0, max_radius_px=0),
    ],
)
def test_ambient_layers_reject_invalid_visual_configuration(factory: object) -> None:
    with pytest.raises(LayerInputError):
        factory()  # type: ignore[operator]


def test_ambient_layer_configuration_is_frozen() -> None:
    layer = RainLayer(0)
    with pytest.raises(FrozenInstanceError):
        layer.seed = 1  # type: ignore[misc]
