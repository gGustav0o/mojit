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
    from PIL import Image, ImageDraw, ImageFont, features

    from mojit.adapters.budoux_segmenter import segment_japanese_phrases

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
                "budoux": budoux_version,
                "japanese_phrases": phrases,
                "raqm": True,
                "fribidi": str(expected_dll),
                "fribidi_sha256": dll_hash,
                "vertical_reference_sha256": rendered_hash,
                "font": str(font_path.resolve()),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
