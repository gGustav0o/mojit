from __future__ import annotations

from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from mojit.core.models import Frame, ModelValidationError, RenderContext, TextMask, Viewport
from mojit.effects.api import (
    EffectConfig,
    EffectInputError,
    TextEffectLayer,
    validate_effect_inputs,
)


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


def test_text_effect_layer_adapts_the_existing_effect_contract_exactly() -> None:
    mask = TextMask(3, 2, np.full((2, 3), 127, dtype=np.uint8))
    context = RenderContext(Viewport(3, 2), 5, 0.625)
    config = EffectConfig(42)
    calls: list[tuple[TextMask, RenderContext, EffectConfig]] = []
    expected = Frame(3, 2, np.zeros((2, 3, 4), dtype=np.uint8))

    def effect(
        received_mask: TextMask,
        received_context: RenderContext,
        received_config: EffectConfig,
    ) -> Frame:
        calls.append((received_mask, received_context, received_config))
        return expected

    layer = TextEffectLayer(mask, effect, config)

    assert layer.render(context) is expected
    assert calls == [(mask, context, config)]
    with pytest.raises(FrozenInstanceError):
        layer.mask = mask  # type: ignore[misc]


@pytest.mark.parametrize(
    ("mask", "effect", "config", "message"),
    [
        (object(), lambda *args: None, EffectConfig(0), "mask"),
        (
            TextMask(1, 1, np.zeros((1, 1), dtype=np.uint8)),
            object(),
            EffectConfig(0),
            "callable",
        ),
        (
            TextMask(1, 1, np.zeros((1, 1), dtype=np.uint8)),
            lambda *args: None,
            object(),
            "config",
        ),
    ],
)
def test_text_effect_layer_rejects_invalid_construction(
    mask: object,
    effect: object,
    config: object,
    message: str,
) -> None:
    with pytest.raises(EffectInputError, match=message):
        TextEffectLayer(mask, effect, config)  # type: ignore[arg-type]


def test_text_effect_layer_validates_context_viewport_before_calling_effect() -> None:
    mask = TextMask(2, 1, np.zeros((1, 2), dtype=np.uint8))
    layer = TextEffectLayer(mask, lambda *args: pytest.fail("effect called"), EffectConfig(0))

    with pytest.raises(EffectInputError, match="dimensions"):
        layer.render(RenderContext(Viewport(3, 1), 0, 0.0))
