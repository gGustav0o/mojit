from __future__ import annotations

import random

import numpy as np
import pytest

from mojit.core.models import ModelValidationError
from mojit.core.randomness import derive_random_seed, make_rng


def test_identical_inputs_produce_identical_local_sequences() -> None:
    first = make_rng(42, "glitch", 7).integers(0, 2**31, size=20)
    second = make_rng(42, "glitch", 7).integers(0, 2**31, size=20)

    assert np.array_equal(first, second)
    assert derive_random_seed(42, "glitch", 7) == 94568124780160671997979395220158858729


def test_each_seed_component_changes_the_stream() -> None:
    baseline = derive_random_seed(42, "glitch", 7)

    assert derive_random_seed(43, "glitch", 7) != baseline
    assert derive_random_seed(42, "pulse", 7) != baseline
    assert derive_random_seed(42, "glitch", 8) != baseline
    assert derive_random_seed(42, "グリッチ", 7) != baseline


def test_generator_creation_does_not_touch_global_random_state() -> None:
    python_before = random.getstate()
    numpy_before = np.random.get_state()

    make_rng(-1, "glitch", 0).random(10)

    assert random.getstate() == python_before
    numpy_after = np.random.get_state()
    assert numpy_after[0] == numpy_before[0]
    assert np.array_equal(numpy_after[1], numpy_before[1])
    assert numpy_after[2:] == numpy_before[2:]


@pytest.mark.parametrize(
    ("seed", "effect_id", "frame_index"),
    [
        (True, "effect", 0),
        (2**63, "effect", 0),
        (0, "", 0),
        (0, 1, 0),
        (0, "effect", -1),
        (0, "effect", True),
    ],
)
def test_invalid_random_inputs_fail_explicitly(
    seed: object,
    effect_id: object,
    frame_index: object,
) -> None:
    with pytest.raises(ModelValidationError):
        derive_random_seed(seed, effect_id, frame_index)  # type: ignore[arg-type]
