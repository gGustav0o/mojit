from __future__ import annotations

import hashlib

import numpy as np

from mojit.adapters.wezterm.cell_encoder import COLOR_MASK, _sample_frame
from mojit.core.models import Orientation, RenderContext, TextMask, Viewport
from mojit.core.scene import Scene, render_scene
from mojit.core.typography import TypographyKey
from mojit.effects.api import EffectConfig, TextEffectLayer
from mojit.effects.neon import render_neon
from mojit.layers.rain import RainLayer
from mojit.layers.stars import StarsLayer
from mojit.scenes.presets import build_scene, scene_names


def _synthetic_japanese_mask(key: TypographyKey) -> TextMask:
    assert key.text == "星雨電脳"
    alpha = np.zeros((key.viewport.height_px, key.viewport.width_px), dtype=np.uint8)
    alpha[
        key.viewport.height_px // 3 : 2 * key.viewport.height_px // 3,
        key.viewport.width_px // 4 : 3 * key.viewport.width_px // 4,
    ] = 255
    return TextMask(key.viewport.width_px, key.viewport.height_px, alpha)


def test_japanese_text_composes_with_two_ambient_layers_deterministically() -> None:
    viewport = Viewport(96, 64)
    font_data = b"synthetic-cjk-font"
    key = TypographyKey(
        text="星雨電脳",
        font_fingerprint=hashlib.sha256(font_data).hexdigest(),
        orientation=Orientation.HORIZONTAL,
        viewport=viewport,
        margin=0.08,
    )
    scene = Scene(
        (
            StarsLayer(seed=101, density=0.003),
            RainLayer(seed=202, density=0.003),
            TextEffectLayer(
                _synthetic_japanese_mask(key),
                render_neon,
                EffectConfig(seed=303),
            ),
        )
    )
    context = RenderContext(viewport, frame_index=12, elapsed_seconds=1.5)

    first = render_scene(scene, context)
    repeated = render_scene(scene, context)
    later = render_scene(scene, RenderContext(viewport, frame_index=13, elapsed_seconds=1.625))

    assert first == repeated
    assert first != later
    assert (first.width, first.height) == (96, 64)
    assert np.count_nonzero(first.rgba[..., 3]) > 0
    assert not first.rgba.flags.writeable


def test_reference_presets_remain_distinct_after_wezterm_cell_sampling() -> None:
    viewport = Viewport(930, 1012)
    context = RenderContext(viewport, frame_index=24, elapsed_seconds=3.0)
    alpha = np.zeros((viewport.height_px, viewport.width_px), dtype=np.uint8)
    alpha[430:580, 265:665] = 255
    text = TextEffectLayer(
        TextMask(viewport.width_px, viewport.height_px, alpha),
        render_neon,
        EffectConfig(seed=42),
    )
    text_cells = _sample_frame(
        render_scene(Scene((text,)), context),
        columns=93,
        rows=44,
    )
    text_cells &= COLOR_MASK

    sampled_presets = []
    for scene_id in scene_names():
        cells = _sample_frame(
            render_scene(build_scene(scene_id, text, 42), context),
            columns=93,
            rows=44,
        )
        cells &= COLOR_MASK
        sampled_presets.append(cells)
        ambient_cells = np.any(cells != text_cells, axis=(2, 3))
        assert np.count_nonzero(ambient_cells) >= 20

    assert all(
        not np.array_equal(left, right)
        for index, left in enumerate(sampled_presets)
        for right in sampled_presets[index + 1 :]
    )
