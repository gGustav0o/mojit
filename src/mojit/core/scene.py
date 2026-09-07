"""Pure ordered composition of independent full-viewport visual layers."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Protocol

from mojit.core.compositor import alpha_composite_many
from mojit.core.models import MAX_SCENE_LAYERS, Frame, RenderContext


class SceneCompositionError(ValueError):
    """A scene or one of its layers violates the composition contract."""


class Layer(Protocol):
    """One pure visual contribution rendered for an explicit frame context."""

    def render(self, context: RenderContext) -> Frame:
        """Render one immutable full-viewport frame."""
        ...


@dataclass(frozen=True, slots=True)
class Scene:
    """An immutable back-to-front sequence of visual layers."""

    layers: tuple[Layer, ...]

    def __post_init__(self) -> None:
        if isinstance(self.layers, (str, bytes)) or not isinstance(self.layers, Sequence):
            raise SceneCompositionError("layers must be a sequence")
        layers = tuple(self.layers)
        if not layers:
            raise SceneCompositionError("scene must contain at least one layer")
        if len(layers) > MAX_SCENE_LAYERS:
            raise SceneCompositionError(f"scene must not exceed {MAX_SCENE_LAYERS} layers")
        if any(not callable(getattr(layer, "render", None)) for layer in layers):
            raise SceneCompositionError("each layer must provide render(context)")
        object.__setattr__(self, "layers", layers)


def render_scene(scene: Scene, context: RenderContext) -> Frame:
    """Render and source-over composite a scene from back to front."""
    if not isinstance(scene, Scene):
        raise SceneCompositionError("scene must be a Scene")
    if not isinstance(context, RenderContext):
        raise SceneCompositionError("context must be a RenderContext")

    expected = (context.viewport.width_px, context.viewport.height_px)

    def rendered_layers() -> Iterator[Frame]:
        for index, layer in enumerate(scene.layers):
            frame = layer.render(context)
            if not isinstance(frame, Frame):
                raise SceneCompositionError(f"layer {index} must return a Frame")
            if (frame.width, frame.height) != expected:
                raise SceneCompositionError(
                    f"layer {index} frame dimensions must match the context viewport"
                )
            yield frame
            del frame

    return alpha_composite_many(rendered_layers())
