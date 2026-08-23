from __future__ import annotations

import pytest

from mojit.effects.chromatic import render_chromatic
from mojit.effects.glitch import render_glitch
from mojit.effects.neon import render_neon
from mojit.effects.pulse import render_pulse
from mojit.effects.registry import EFFECTS, UnknownEffectError, effect_names, get_effect


def test_registry_is_complete_stable_and_exact() -> None:
    assert effect_names() == ("chromatic", "glitch", "neon", "pulse")
    assert get_effect("chromatic") is render_chromatic
    assert get_effect("glitch") is render_glitch
    assert get_effect("neon") is render_neon
    assert get_effect("pulse") is render_pulse


def test_registry_is_immutable() -> None:
    with pytest.raises(TypeError):
        EFFECTS["new"] = render_neon  # type: ignore[index]


@pytest.mark.parametrize("effect_id", ["unknown", "Neon", "", None])
def test_registry_rejects_unknown_values_without_fallback(effect_id: object) -> None:
    with pytest.raises(UnknownEffectError, match="unknown effect"):
        get_effect(effect_id)  # type: ignore[arg-type]
