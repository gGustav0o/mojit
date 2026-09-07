"""Standalone process-memory probe for sustained scene rendering on Windows."""

from __future__ import annotations

import argparse
import gc
import json
import math
import time
from pathlib import Path

import numpy as np
from process_memory import current_process_memory


def _positive_real(value: str) -> float:
    converted = float(value)
    if not math.isfinite(converted) or converted <= 0.0:
        raise argparse.ArgumentTypeError("must be a finite positive number")
    return converted


def _positive_int(value: str) -> int:
    converted = int(value)
    if converted <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return converted


def _slope(samples: list[dict[str, int | float]], field: str) -> float:
    tail = samples[len(samples) // 2 :]
    if len(tail) < 2:
        return 0.0
    x_mean = sum(float(item["elapsed_seconds"]) for item in tail) / len(tail)
    y_mean = sum(float(item[field]) for item in tail) / len(tail)
    denominator = sum((float(item["elapsed_seconds"]) - x_mean) ** 2 for item in tail)
    if denominator == 0.0:
        return 0.0
    numerator = sum(
        (float(item["elapsed_seconds"]) - x_mean) * (float(item[field]) - y_mean) for item in tail
    )
    return numerator / denominator


def main() -> int:
    from mojit.native_runtime import activate_native_runtime

    activate_native_runtime()
    from mojit.core.models import MAX_SCENE_LAYERS, RenderContext, TextMask, Viewport
    from mojit.core.scene import render_scene
    from mojit.effects.api import EffectConfig, TextEffectLayer
    from mojit.effects.neon import render_neon
    from mojit.scenes.presets import build_custom_scene, build_scene, scene_names

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration-seconds", type=_positive_real, default=600.0)
    parser.add_argument("--sample-interval-seconds", type=_positive_real, default=10.0)
    parser.add_argument("--width", type=_positive_int, default=1920)
    parser.add_argument("--height", type=_positive_int, default=1080)
    parser.add_argument("--fps", type=_positive_int, default=8)
    parser.add_argument("--warmup-frames", type=int, default=30)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--scene", choices=scene_names(), default="rainy-night")
    selection.add_argument("--layer-count", type=_positive_int)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    if arguments.warmup_frames < 0:
        parser.error("--warmup-frames must be non-negative")
    if arguments.layer_count is not None and arguments.layer_count > MAX_SCENE_LAYERS:
        parser.error(f"--layer-count must not exceed {MAX_SCENE_LAYERS}")

    viewport = Viewport(arguments.width, arguments.height)
    alpha = np.zeros((viewport.height_px, viewport.width_px), dtype=np.uint8)
    alpha[
        viewport.height_px // 3 : 2 * viewport.height_px // 3,
        viewport.width_px // 4 : 3 * viewport.width_px // 4,
    ] = 255
    text = TextEffectLayer(
        TextMask(viewport.width_px, viewport.height_px, alpha),
        render_neon,
        EffectConfig(seed=42),
    )
    if arguments.layer_count is None:
        scene = build_scene(arguments.scene, text, 42)
        scene_label = arguments.scene
    else:
        ambient_ids = ("stars", "rain", "snow")
        layers = tuple(
            ambient_ids[index % len(ambient_ids)] for index in range(arguments.layer_count - 1)
        ) + ("text",)
        scene = build_custom_scene(layers, text, 42)
        scene_label = f"custom-{arguments.layer_count}-layers"

    frame_index = 0
    for frame_index in range(arguments.warmup_frames):
        render_scene(
            scene,
            RenderContext(viewport, frame_index, frame_index / arguments.fps),
        )
    del frame_index
    gc.collect()

    samples: list[dict[str, int | float]] = []
    started = time.perf_counter()
    next_sample = started
    rendered_frames = 0
    last_frame = None
    while True:
        now = time.perf_counter()
        if now >= next_sample:
            memory = current_process_memory()
            samples.append(
                {
                    "elapsed_seconds": now - started,
                    "frame_index": rendered_frames,
                    "working_set_bytes": memory.working_set_bytes,
                    "private_bytes": memory.private_bytes,
                }
            )
            next_sample += arguments.sample_interval_seconds
        if now - started >= arguments.duration_seconds:
            break
        last_frame = render_scene(
            scene,
            RenderContext(viewport, rendered_frames, rendered_frames / arguments.fps),
        )
        rendered_frames += 1
    del last_frame
    gc.collect()
    final_memory = current_process_memory()
    elapsed = time.perf_counter() - started
    samples.append(
        {
            "elapsed_seconds": elapsed,
            "frame_index": rendered_frames,
            "working_set_bytes": final_memory.working_set_bytes,
            "private_bytes": final_memory.private_bytes,
        }
    )

    metrics = {
        "process_id": final_memory.pid,
        "scene": scene_label,
        "viewport": [viewport.width_px, viewport.height_px],
        "duration_seconds": elapsed,
        "rendered_frames": rendered_frames,
        "samples": samples,
        "working_set_delta_bytes": samples[-1]["working_set_bytes"]
        - samples[0]["working_set_bytes"],
        "private_bytes_delta": samples[-1]["private_bytes"] - samples[0]["private_bytes"],
        "peak_working_set_bytes": max(int(item["working_set_bytes"]) for item in samples),
        "peak_private_bytes": max(int(item["private_bytes"]) for item in samples),
        "tail_working_set_slope_bytes_per_second": _slope(samples, "working_set_bytes"),
        "tail_private_slope_bytes_per_second": _slope(samples, "private_bytes"),
    }
    document = json.dumps(metrics, sort_keys=True)
    if arguments.output is not None:
        arguments.output.write_text(document, encoding="utf-8")
    print(document)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
