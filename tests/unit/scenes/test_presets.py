from __future__ import annotations

import numpy as np
import pytest

from mojit.core.models import MAX_SCENE_LAYERS, Frame, RenderContext, TextMask, Viewport
from mojit.core.scene import render_scene
from mojit.effects.api import EffectConfig, TextEffectLayer
from mojit.effects.neon import render_neon
from mojit.scenes.presets import (
    SCENES,
    UnknownSceneError,
    build_custom_scene,
    build_scene,
    get_scene_builder,
    scene_names,
)


def _text_layer(viewport: Viewport) -> TextEffectLayer:
    alpha = np.zeros((viewport.height_px, viewport.width_px), dtype=np.uint8)
    alpha[2:-2, 2:-2] = 255
    return TextEffectLayer(
        TextMask(viewport.width_px, viewport.height_px, alpha), render_neon, EffectConfig(9)
    )


def test_scene_registry_is_immutable_complete_and_stably_sorted() -> None:
    assert scene_names() == ("rainy-night", "snowfall", "space")
    with pytest.raises(TypeError):
        SCENES["other"] = get_scene_builder("space")  # type: ignore[index]


@pytest.mark.parametrize("scene_id", scene_names())
@pytest.mark.parametrize("seed", [-(2**63), 2**63 - 1])
def test_presets_build_deterministic_multi_layer_scenes(scene_id: str, seed: int) -> None:
    viewport = Viewport(64, 48)
    context = RenderContext(viewport, 7, 0.875)
    text = _text_layer(viewport)

    first = render_scene(build_scene(scene_id, text, seed), context)
    repeated = render_scene(build_scene(scene_id, text, seed), context)

    assert first == repeated
    assert isinstance(first, Frame)
    assert not first.rgba.flags.writeable


def test_scene_registry_rejects_unknown_names_and_invalid_text_layer() -> None:
    with pytest.raises(UnknownSceneError, match="rainy-night, snowfall, space"):
        get_scene_builder("unknown")
    with pytest.raises(TypeError, match="TextEffectLayer"):
        build_scene("space", object(), 0)  # type: ignore[arg-type]


def test_custom_scene_preserves_order_and_derives_distinct_duplicate_layers() -> None:
    viewport = Viewport(64, 48)
    text = _text_layer(viewport)
    scene = build_custom_scene(("stars", "rain", "rain", "text"), text, 42)

    assert [type(layer).__name__ for layer in scene.layers] == [
        "StarsLayer",
        "RainLayer",
        "RainLayer",
        "TextEffectLayer",
    ]
    assert scene.layers[1] != scene.layers[2]


def test_custom_scene_builder_rejects_invalid_direct_calls() -> None:
    viewport = Viewport(8, 6)
    with pytest.raises(ValueError, match="non-empty"):
        build_custom_scene((), _text_layer(viewport), 0)
    with pytest.raises(TypeError, match="TextEffectLayer"):
        build_custom_scene(("text",), object(), 0)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="exactly one text"):
        build_custom_scene(("stars",), _text_layer(viewport), 0)
    with pytest.raises(ValueError, match="exactly one text"):
        build_custom_scene(("text", "text"), _text_layer(viewport), 0)
    with pytest.raises(ValueError, match="unknown"):
        build_custom_scene(("unknown", "text"), _text_layer(viewport), 0)
    with pytest.raises(ValueError, match=str(MAX_SCENE_LAYERS)):
        build_custom_scene(
            ("stars",) * MAX_SCENE_LAYERS + ("text",),
            _text_layer(viewport),
            0,
        )
