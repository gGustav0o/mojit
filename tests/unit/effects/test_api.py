from __future__ import annotations

from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from mojit.core.models import ModelValidationError, RenderContext, TextMask, Viewport
from mojit.effects.api import EffectConfig, EffectInputError, validate_effect_inputs


@pytest.mark.parametrize("seed", [-(2**63), 0, 2**63 - 1])
def test_effect_config_accepts_signed_64_bit_boundaries(seed: int) -> None:
    config = EffectConfig(seed)
    assert config.seed == seed
    with pytest.raises(FrozenInstanceError):
        config.seed = 1  # type: ignore[misc]


@pytest.mark.parametrize("seed", [-(2**63) - 1, 2**63, True, 1.5, "0"])
def test_effect_config_rejects_invalid_seed(seed: object) -> None:
    with pytest.raises(ModelValidationError):
        EffectConfig(seed)  # type: ignore[arg-type]


def test_common_effect_input_validation_returns_typed_values() -> None:
    mask = TextMask(3, 2, np.zeros((2, 3), dtype=np.uint8))
    context = RenderContext(Viewport(3, 2), 0, 0.0)
    config = EffectConfig(0)
    assert validate_effect_inputs(mask, context, config) == (mask, context, config)


@pytest.mark.parametrize(
    ("mask", "context", "config", "message"),
    [
        (object(), RenderContext(Viewport(3, 2), 0, 0.0), EffectConfig(0), "mask"),
        (TextMask(3, 2, np.zeros((2, 3), dtype=np.uint8)), object(), EffectConfig(0), "context"),
        (
            TextMask(3, 2, np.zeros((2, 3), dtype=np.uint8)),
            RenderContext(Viewport(3, 2), 0, 0.0),
            object(),
            "config",
        ),
        (
            TextMask(3, 2, np.zeros((2, 3), dtype=np.uint8)),
            RenderContext(Viewport(4, 2), 0, 0.0),
            EffectConfig(0),
            "dimensions",
        ),
    ],
)
def test_common_effect_input_validation_rejects_invalid_values(
    mask: object, context: object, config: object, message: str
) -> None:
    with pytest.raises(EffectInputError, match=message):
        validate_effect_inputs(mask, context, config)
