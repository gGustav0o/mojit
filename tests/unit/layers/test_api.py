from __future__ import annotations

import math
import sys

import numpy as np
import pytest

from mojit.core.compositor import RgbaColor
from mojit.core.models import RenderContext, Viewport
from mojit.layers.api import (
    MAX_PARTICLES_PER_LAYER,
    LayerInputError,
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


def test_particle_count_is_viewport_relative_zeroable_and_hard_capped() -> None:
    viewport = Viewport(100, 50)
    assert particle_count(viewport, 0.0) == 0
    assert particle_count(viewport, 0.00001) == 1
    assert particle_count(viewport, 0.01) == 50
    assert particle_count(Viewport(100_000, 100_000), 0.1) == MAX_PARTICLES_PER_LAYER


def test_periodic_motion_reduces_time_before_multiplication() -> None:
    distance = periodic_distance(
        sys.float_info.max,
        sys.float_info.max,
        73.0,
        rate_factor=1.25,
    )
    phase = periodic_phase(sys.float_info.max, 20.0)

    assert math.isfinite(distance) and 0.0 <= distance < 73.0
    assert math.isfinite(phase) and 0.0 <= phase < math.tau
    assert periodic_distance(sys.float_info.max, 0.0, 73.0) == 0.0
    assert periodic_phase(sys.float_info.max, 0.0) == 0.0


def test_transparent_rgba_matches_viewport_without_shared_storage() -> None:
    viewport = Viewport(3, 2)
    first = transparent_rgba(viewport)
    second = transparent_rgba(viewport)
    first[0, 0] = 255

    assert first.shape == second.shape == (2, 3, 4)
    assert first.dtype == second.dtype == np.uint8
    assert np.count_nonzero(second) == 0


def test_layer_validators_normalize_valid_values() -> None:
    context = RenderContext(Viewport(2, 1), 0, 0.0)
    color = RgbaColor(1, 2, 3, 4)
    assert validate_context(context) is context
    assert validate_seed(np.int64(-4)) == -4
    assert validate_real(np.float64(0.25), name="ratio", maximum=1.0) == 0.25
    assert validate_int(np.int64(3), name="count", minimum=1, maximum=4) == 3
    assert validate_color(color) is color


@pytest.mark.parametrize("value", [True, 1.5, -(2**63) - 1, 2**63])
def test_seed_validation_rejects_invalid_values(value: object) -> None:
    with pytest.raises(LayerInputError, match="seed"):
        validate_seed(value)


@pytest.mark.parametrize("value", [True, "1", -0.1, float("nan"), float("inf"), 1.1])
def test_real_validation_rejects_invalid_values(value: object) -> None:
    with pytest.raises(LayerInputError, match="ratio"):
        validate_real(value, name="ratio", maximum=1.0)


@pytest.mark.parametrize("value", [True, 1.5, "1", 0, 5])
def test_int_validation_rejects_invalid_values(value: object) -> None:
    with pytest.raises(LayerInputError, match="count"):
        validate_int(value, name="count", minimum=1, maximum=4)


def test_context_and_color_validation_reject_untyped_values() -> None:
    with pytest.raises(LayerInputError, match="context"):
        validate_context(object())
    with pytest.raises(LayerInputError, match="color"):
        validate_color((1, 2, 3, 4))
