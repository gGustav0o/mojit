"""Probe an installed artifact without importing the source checkout."""

from __future__ import annotations

import ctypes
import hashlib
import importlib.metadata
import json
import os
import sys
from pathlib import Path

EXPECTED_DLL_SHA256 = "4283ba30461395fdf46399b2665176e6f41d11bc7bf6977188120152fde31fd2"


def _loaded_modules() -> list[Path]:
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    psapi.EnumProcessModulesEx.argtypes = (
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_ulong),
        ctypes.c_ulong,
    )
    psapi.EnumProcessModulesEx.restype = ctypes.c_int
    psapi.GetModuleFileNameExW.argtypes = (
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_wchar_p,
        ctypes.c_ulong,
    )
    psapi.GetModuleFileNameExW.restype = ctypes.c_ulong
    process = kernel32.GetCurrentProcess()
    capacity = 2048
    modules = (ctypes.c_void_p * capacity)()
    needed = ctypes.c_ulong()
    if not psapi.EnumProcessModulesEx(
        process, modules, ctypes.sizeof(modules), ctypes.byref(needed), 3
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    result: list[Path] = []
    for module in modules[: needed.value // ctypes.sizeof(ctypes.c_void_p)]:
        buffer = ctypes.create_unicode_buffer(32768)
        if psapi.GetModuleFileNameExW(process, module, buffer, len(buffer)):
            result.append(Path(buffer.value).resolve())
    return result


def main() -> int:
    from mojit.native_runtime import activate_native_runtime

    runtime = activate_native_runtime()
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont, features

    from mojit import __version__
    from mojit.adapters.budoux_segmenter import segment_japanese_phrases
    from mojit.config.toml import parse_toml_config
    from mojit.core.models import RenderContext, TextMask, Viewport
    from mojit.core.scene import render_scene
    from mojit.effects.api import EffectConfig, TextEffectLayer
    from mojit.effects.neon import render_neon
    from mojit.scenes.presets import build_custom_scene, build_scene, scene_names

    mojit_version = importlib.metadata.version("mojit")
    if __version__ != mojit_version:
        raise RuntimeError("package version does not match installed metadata")

    budoux_version = importlib.metadata.version("budoux")
    if budoux_version != "0.9.0":
        raise RuntimeError(f"unexpected installed BudouX version: {budoux_version}")
    phrases = segment_japanese_phrases("僕の心のヤバイやつ")
    if phrases != ("僕の", "心の", "ヤバイや", "つ"):
        raise RuntimeError(f"unexpected BudouX Japanese segmentation: {phrases}")

    if not features.check_feature("raqm"):
        raise RuntimeError("installed Pillow has no Raqm support")
    font_path = Path(os.environ.get("MOJIT_PROBE_FONT", "C:/Windows/Fonts/YuGothB.ttc"))
    font = ImageFont.truetype(str(font_path), 96, layout_engine=ImageFont.Layout.RAQM)
    image = Image.new("L", (512, 512))
    draw = ImageDraw.Draw(image)
    draw.text((32, 16), "電脳世界", fill=255, font=font, direction="ttb", language="ja")
    rendered_hash = hashlib.sha256(image.tobytes()).hexdigest()

    scene_config = parse_toml_config('scene_version = 1\nlayers = ["stars", "rain", "text"]\n')
    if scene_config.scene_layers != ("stars", "rain", "text"):
        raise RuntimeError("installed custom scene parsing failed")
    viewport = Viewport(96, 64)
    alpha = np.zeros((viewport.height_px, viewport.width_px), dtype=np.uint8)
    alpha[20:44, 28:68] = 255
    text_layer = TextEffectLayer(
        TextMask(viewport.width_px, viewport.height_px, alpha),
        render_neon,
        EffectConfig(seed=42),
    )
    scene = build_custom_scene(scene_config.scene_layers, text_layer, seed=42)
    context = RenderContext(viewport, frame_index=12, elapsed_seconds=1.5)
    scene_frame = render_scene(scene, context)
    scene_deterministic = scene_frame == render_scene(scene, context)
    if not scene_deterministic or not np.any(scene_frame.rgba[..., 3]):
        raise RuntimeError("installed scene rendering failed")
    scene_hash = hashlib.sha256(scene_frame.rgba.tobytes()).hexdigest()
    built_in_scenes_rendered = []
    for scene_id in scene_names():
        built_in = build_scene(scene_id, text_layer, seed=42)
        built_in_frame = render_scene(built_in, context)
        if built_in_frame != render_scene(built_in, context):
            raise RuntimeError(f"installed built-in scene is not deterministic: {scene_id}")
        built_in_scenes_rendered.append(scene_id)

    expected_dll = runtime.fribidi_dll.resolve()
    loaded = [path for path in _loaded_modules() if path.name.lower() == "libfribidi-0.dll"]
    if loaded != [expected_dll]:
        raise RuntimeError(
            f"unexpected loaded FriBiDi module(s): {loaded}; expected {expected_dll}"
        )
    dll_hash = hashlib.sha256(expected_dll.read_bytes()).hexdigest()
    if dll_hash != EXPECTED_DLL_SHA256:
        raise RuntimeError(f"installed FriBiDi hash mismatch: {dll_hash}")

    print(
        json.dumps(
            {
                "python": sys.version.split()[0],
                "implementation": sys.implementation.name,
                "mojit_version": mojit_version,
                "budoux": budoux_version,
                "japanese_phrases": phrases,
                "raqm": True,
                "fribidi": str(expected_dll),
                "fribidi_sha256": dll_hash,
                "vertical_reference_sha256": rendered_hash,
                "font": str(font_path.resolve()),
                "scene_config_layers": list(scene_config.scene_layers),
                "scene_frame_sha256": scene_hash,
                "scene_render_deterministic": scene_deterministic,
                "built_in_scenes_rendered": built_in_scenes_rendered,
                "scenes": list(scene_names()),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
