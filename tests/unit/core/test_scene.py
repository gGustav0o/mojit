from __future__ import annotations

import gc
import weakref
from dataclasses import FrozenInstanceError, dataclass

import numpy as np
import pytest

from mojit.core.models import MAX_SCENE_LAYERS, Frame, RenderContext, Viewport
from mojit.core.scene import Layer, Scene, SceneCompositionError, render_scene


def _frame(viewport: Viewport, rgba: tuple[int, int, int, int]) -> Frame:
    values = np.empty((viewport.height_px, viewport.width_px, 4), dtype=np.uint8)
    values[:] = rgba
    return Frame(viewport.width_px, viewport.height_px, values)


@dataclass(frozen=True, slots=True)
class _SolidLayer:
    rgba: tuple[int, int, int, int]

    def render(self, context: RenderContext) -> Frame:
        return _frame(context.viewport, self.rgba)


def test_scene_composes_two_independent_layers_deterministically_back_to_front() -> None:
    context = RenderContext(Viewport(3, 2), frame_index=7, elapsed_seconds=0.875)
    scene = Scene((_SolidLayer((255, 0, 0, 255)), _SolidLayer((0, 0, 255, 128))))

    first = render_scene(scene, context)
    repeated = render_scene(scene, context)

    assert first == repeated
    assert first.rgba[0, 0].tolist() == [127, 0, 128, 255]
    assert not first.rgba.flags.writeable
    assert render_scene(Scene(tuple(reversed(scene.layers))), context) != first


def test_single_layer_scene_preserves_the_layer_frame_exactly() -> None:
    context = RenderContext(Viewport(2, 1), 0, 0.0)
    expected = _frame(context.viewport, (11, 22, 33, 44))

    @dataclass(frozen=True, slots=True)
    class FixedLayer:
        def render(self, received: RenderContext) -> Frame:
            assert received is context
            return expected

    assert render_scene(Scene((FixedLayer(),)), context) is expected


def test_scene_normalizes_layers_to_an_immutable_tuple() -> None:
    layers: list[Layer] = [_SolidLayer((0, 0, 0, 0))]
    scene = Scene(layers)  # type: ignore[arg-type]
    layers.append(_SolidLayer((255, 255, 255, 255)))

    assert len(scene.layers) == 1
    with pytest.raises(FrozenInstanceError):
        scene.layers = ()  # type: ignore[misc]


@pytest.mark.parametrize("layers", [(), "bad", (object(),)])
def test_scene_rejects_invalid_layer_sequences(layers: object) -> None:
    with pytest.raises(SceneCompositionError):
        Scene(layers)  # type: ignore[arg-type]


def test_scene_rejects_more_than_the_bounded_layer_limit() -> None:
    layers = (_SolidLayer((0, 0, 0, 0)),) * (MAX_SCENE_LAYERS + 1)

    with pytest.raises(SceneCompositionError, match=str(MAX_SCENE_LAYERS)):
        Scene(layers)


def test_maximum_layer_scene_streams_larger_frames_with_bounded_live_inputs() -> None:
    viewport = Viewport(960, 540)
    context = RenderContext(viewport, 1_000_000, 1_000_000.0)
    arrays: list[weakref.ReferenceType[np.ndarray]] = []
    live_before_render: list[int] = []

    @dataclass(frozen=True, slots=True)
    class TrackingLayer:
        index: int

        def render(self, received: RenderContext) -> Frame:
            assert received is context
            gc.collect()
            live_before_render.append(sum(reference() is not None for reference in arrays))
            values = np.zeros((viewport.height_px, viewport.width_px, 4), dtype=np.uint8)
            values[..., self.index % 3] = self.index * 7
            values[..., 3] = 32
            frame = Frame(viewport.width_px, viewport.height_px, values)
            arrays.append(weakref.ref(frame.rgba))
            return frame

    result = render_scene(
        Scene(tuple(TrackingLayer(index) for index in range(MAX_SCENE_LAYERS))),
        context,
    )
    gc.collect()

    assert result.rgba.shape == (540, 960, 4)
    assert max(live_before_render) <= 1
    assert all(reference() is None for reference in arrays)


def test_render_scene_rejects_invalid_boundaries_and_layer_results() -> None:
    context = RenderContext(Viewport(2, 1), 0, 0.0)

    class InvalidResultLayer:
        def render(self, received: RenderContext) -> object:
            del received
            return object()

    class WrongViewportLayer:
        def render(self, received: RenderContext) -> Frame:
            del received
            return _frame(Viewport(1, 1), (0, 0, 0, 0))

    with pytest.raises(SceneCompositionError, match="scene must"):
        render_scene(object(), context)  # type: ignore[arg-type]
    with pytest.raises(SceneCompositionError, match="context"):
        render_scene(Scene((_SolidLayer((0, 0, 0, 0)),)), object())  # type: ignore[arg-type]
    with pytest.raises(SceneCompositionError, match="return a Frame"):
        render_scene(Scene((InvalidResultLayer(),)), context)  # type: ignore[arg-type]
    with pytest.raises(SceneCompositionError, match="dimensions"):
        render_scene(Scene((WrongViewportLayer(),)), context)
