"""Minimal immutable contract shared by all effects."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from mojit.core.models import Frame, ModelValidationError, RenderContext, TextMask, require_int


class EffectInputError(ValueError):
    """Effect inputs do not describe one compatible viewport."""


@dataclass(frozen=True, slots=True)
class EffectConfig:
    """Cross-effect runtime values available in v1."""

    seed: int

    def __post_init__(self) -> None:
        seed = require_int(self.seed, name="seed", minimum=-(2**63))
        if seed >= 2**63:
            raise ModelValidationError("seed must be < 2**63")
        object.__setattr__(self, "seed", seed)


Effect = Callable[[TextMask, RenderContext, EffectConfig], Frame]


@dataclass(frozen=True, slots=True)
class TextEffectLayer:
    """Adapt one v1 text mask/effect pair to the scene-layer contract."""

    mask: TextMask
    effect: Effect
    config: EffectConfig

    def __post_init__(self) -> None:
        if not isinstance(self.mask, TextMask):
            raise EffectInputError("mask must be a TextMask")
        if not callable(self.effect):
            raise EffectInputError("effect must be callable")
        if not isinstance(self.config, EffectConfig):
            raise EffectInputError("config must be an EffectConfig")

    def render(self, context: RenderContext) -> Frame:
        """Render the captured text contribution for an explicit context."""
        mask, validated_context, config = validate_effect_inputs(self.mask, context, self.config)
        return self.effect(mask, validated_context, config)


def validate_effect_inputs(
    mask: object,
    context: object,
    config: object,
) -> tuple[TextMask, RenderContext, EffectConfig]:
    """Validate the common effect boundary once."""
    if not isinstance(mask, TextMask):
        raise EffectInputError("mask must be a TextMask")
    if not isinstance(context, RenderContext):
        raise EffectInputError("context must be a RenderContext")
    if not isinstance(config, EffectConfig):
        raise EffectInputError("config must be an EffectConfig")
    if (mask.width, mask.height) != (
        context.viewport.width_px,
        context.viewport.height_px,
    ):
        raise EffectInputError("mask dimensions must match context viewport")
    return mask, context, config
