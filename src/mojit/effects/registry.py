"""Explicit immutable v1 effect-name-to-renderer mapping."""

from __future__ import annotations

from types import MappingProxyType

from mojit.effects.api import Effect
from mojit.effects.chromatic import render_chromatic
from mojit.effects.glitch import render_glitch
from mojit.effects.neon import render_neon
from mojit.effects.pulse import render_pulse


class UnknownEffectError(LookupError):
    """A syntactically valid effect identifier is not registered."""


EFFECTS: MappingProxyType[str, Effect] = MappingProxyType(
    {
        "neon": render_neon,
        "glitch": render_glitch,
        "chromatic": render_chromatic,
        "pulse": render_pulse,
    }
)


def effect_names() -> tuple[str, ...]:
    """Return stable user-facing effect identifiers."""
    return tuple(sorted(EFFECTS))


def get_effect(effect_id: str) -> Effect:
    """Return an exact registered renderer without fallback."""
    try:
        return EFFECTS[effect_id]
    except (KeyError, TypeError) as error:
        available = ", ".join(effect_names())
        raise UnknownEffectError(
            f"unknown effect {effect_id!r}; choose one of: {available}"
        ) from error
