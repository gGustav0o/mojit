"""Non-interactive smoke checks used against source and an installed wheel."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json

import numpy as np


def main() -> int:
    import mojit

    installed_version = importlib.metadata.version("mojit")
    if mojit.__version__ != installed_version:
        raise RuntimeError("package version does not match installed metadata")
    from mojit.native_runtime import activate_native_runtime

    activate_native_runtime()
    from mojit.config.toml import parse_toml_config
    from mojit.core.models import RenderContext, TextMask, Viewport
    from mojit.core.scene import render_scene
    from mojit.effects.api import EffectConfig, TextEffectLayer
    from mojit.effects.neon import render_neon
    from mojit.scenes.presets import build_custom_scene, build_scene, scene_names

    config = parse_toml_config('scene_version = 1\nlayers = ["stars", "rain", "text"]\n')
    if config.scene_layers != ("stars", "rain", "text"):
        raise RuntimeError("custom scene configuration did not round-trip")

    viewport = Viewport(96, 64)
    alpha = np.zeros((viewport.height_px, viewport.width_px), dtype=np.uint8)
    alpha[20:44, 28:68] = 255
    text = TextEffectLayer(
        TextMask(viewport.width_px, viewport.height_px, alpha),
        render_neon,
        EffectConfig(seed=42),
    )
    scene = build_custom_scene(config.scene_layers, text, seed=42)
    context = RenderContext(viewport, frame_index=12, elapsed_seconds=1.5)
    frame = render_scene(scene, context)
    repeated = render_scene(scene, context)
    if frame != repeated or frame.rgba.flags.writeable or not np.any(frame.rgba[..., 3]):
        raise RuntimeError("installed scene rendering contract failed")

    built_in_scenes_rendered = []
    for scene_id in scene_names():
        built_in = build_scene(scene_id, text, seed=42)
        built_in_frame = render_scene(built_in, context)
        if built_in_frame != render_scene(built_in, context):
            raise RuntimeError(f"installed built-in scene is not deterministic: {scene_id}")
        built_in_scenes_rendered.append(scene_id)

    print(
        json.dumps(
            {
                "custom_layers": list(config.scene_layers),
                "built_in_scenes_rendered": built_in_scenes_rendered,
                "frame_sha256": hashlib.sha256(frame.rgba.tobytes()).hexdigest(),
                "mojit_version": installed_version,
                "scenes": list(scene_names()),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
