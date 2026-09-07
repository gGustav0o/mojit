"""Small explicit registry of built-in ambient scene compositions."""

from __future__ import annotations

from collections.abc import Callable
from types import MappingProxyType

from mojit.core.models import MAX_SCENE_LAYERS
from mojit.core.randomness import derive_random_seed
from mojit.core.scene import Scene
from mojit.effects.api import TextEffectLayer
from mojit.layers.rain import RainLayer
from mojit.layers.snow import SnowLayer
from mojit.layers.stars import StarsLayer


class UnknownSceneError(LookupError):
    """A requested built-in scene is not registered."""


SceneBuilder = Callable[[TextEffectLayer, int], Scene]


def _layer_seed(seed: int, name: str) -> int:
    value = derive_random_seed(seed, f"scene:{name}", 0) & ((1 << 64) - 1)
    return value if value < 2**63 else value - 2**64


def _rainy_night(text: TextEffectLayer, seed: int) -> Scene:
    return Scene(
        (
            StarsLayer(
                _layer_seed(seed, "rainy-night:stars"),
                density=0.00008,
                radius_px=3,
            ),
            RainLayer(
                _layer_seed(seed, "rainy-night:rain"),
                density=0.00022,
                streak_length_px=24,
                streak_width_px=3,
                slant_px=-5,
            ),
            text,
        )
    )


def _space(text: TextEffectLayer, seed: int) -> Scene:
    return Scene(
        (
            StarsLayer(
                _layer_seed(seed, "space:stars"),
                density=0.00014,
                twinkle_hz=0.35,
                radius_px=5,
            ),
            text,
        )
    )


def _snowfall(text: TextEffectLayer, seed: int) -> Scene:
    return Scene(
        (
            StarsLayer(
                _layer_seed(seed, "snowfall:stars"),
                density=0.00006,
                twinkle_hz=0.2,
            ),
            SnowLayer(_layer_seed(seed, "snowfall:snow"), density=0.00016),
            text,
        )
    )


SCENES: MappingProxyType[str, SceneBuilder] = MappingProxyType(
    {
        "rainy-night": _rainy_night,
        "snowfall": _snowfall,
        "space": _space,
    }
)


def scene_names() -> tuple[str, ...]:
    """Return stable user-facing built-in scene identifiers."""
    return tuple(sorted(SCENES))


def get_scene_builder(scene_id: str) -> SceneBuilder:
    """Return one exact preset builder without fallback."""
    try:
        return SCENES[scene_id]
    except (KeyError, TypeError) as error:
        available = ", ".join(scene_names())
        raise UnknownSceneError(
            f"unknown scene {scene_id!r}; choose one of: {available}"
        ) from error


def build_scene(scene_id: str, text: TextEffectLayer, seed: int) -> Scene:
    """Build one deterministic preset around the supplied text layer."""
    if not isinstance(text, TextEffectLayer):
        raise TypeError("text must be a TextEffectLayer")
    return get_scene_builder(scene_id)(text, seed)


def build_custom_scene(
    layer_ids: tuple[str, ...],
    text: TextEffectLayer,
    seed: int,
) -> Scene:
    """Build an ordered version-1 custom scene from product layer identifiers."""
    if not isinstance(layer_ids, tuple) or not layer_ids:
        raise ValueError("layer_ids must be a non-empty tuple")
    if len(layer_ids) > MAX_SCENE_LAYERS:
        raise ValueError(f"layer_ids must not exceed {MAX_SCENE_LAYERS} entries")
    if not isinstance(text, TextEffectLayer):
        raise TypeError("text must be a TextEffectLayer")
    if layer_ids.count("text") != 1:
        raise ValueError("layer_ids must contain exactly one text layer")

    layers = []
    for index, layer_id in enumerate(layer_ids):
        layer_seed = _layer_seed(seed, f"custom:{index}:{layer_id}")
        if layer_id == "text":
            layers.append(text)
        elif layer_id == "rain":
            layers.append(RainLayer(layer_seed))
        elif layer_id == "snow":
            layers.append(SnowLayer(layer_seed))
        elif layer_id == "stars":
            layers.append(StarsLayer(layer_seed))
        else:
            raise ValueError(f"unknown custom scene layer: {layer_id!r}")
    return Scene(tuple(layers))
