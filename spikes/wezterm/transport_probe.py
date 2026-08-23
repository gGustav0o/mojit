"""Offline benchmark for candidate WezTerm frame transports."""

from __future__ import annotations

import argparse
import io
import json
import statistics
import sys
import time
import tracemalloc
import zlib
from collections.abc import Callable
from typing import Any

import numpy as np
from PIL import Image
from protocol import iterm_image, kitty_image

Encoder = Callable[[np.ndarray], bytes]


def _frame(width: int, height: int, pattern: str, index: int) -> np.ndarray:
    if pattern == "high-change":
        rng = np.random.Generator(np.random.PCG64(index + 1))
        return rng.integers(0, 256, size=(height, width, 4), dtype=np.uint8)

    x = np.linspace(0, 255, width, dtype=np.uint8)[None, :]
    y = np.linspace(0, 255, height, dtype=np.uint8)[:, None]
    frame = np.empty((height, width, 4), dtype=np.uint8)
    frame[..., 0] = (x.astype(np.uint16) + index * 3) % 256
    frame[..., 1] = (y.astype(np.uint16) + index * 5) % 256
    frame[..., 2] = ((x.astype(np.uint16) // 2 + y.astype(np.uint16) // 2) + index) % 256
    if pattern == "alpha-heavy":
        frame[..., 3] = ((x.astype(np.uint16) + y.astype(np.uint16)) // 2) % 256
    else:
        frame[..., 3] = 255
    return frame


def _png(frame: np.ndarray) -> bytes:
    stream = io.BytesIO()
    Image.fromarray(frame, mode="RGBA").save(stream, format="PNG", compress_level=1)
    return stream.getvalue()


def _kitty_zlib(frame: np.ndarray) -> bytes:
    height, width, _ = frame.shape
    payload = zlib.compress(frame.tobytes(), level=1)
    return kitty_image(
        payload,
        image_id=1729,
        image_format=32,
        width=width,
        height=height,
        compressed=True,
    )


def _kitty_png(frame: np.ndarray) -> bytes:
    height, width, _ = frame.shape
    return kitty_image(
        _png(frame),
        image_id=1729,
        image_format=100,
        width=width,
        height=height,
        compressed=False,
    )


def _iterm_png(frame: np.ndarray) -> bytes:
    return iterm_image(_png(frame))


def _measure(
    encoder: Encoder,
    *,
    width: int,
    height: int,
    pattern: str,
    frames: int,
) -> dict[str, Any]:
    timings: list[float] = []
    sizes: list[int] = []
    for index in range(frames + 1):
        frame = _frame(width, height, pattern, index)
        start = time.perf_counter()
        encoded = encoder(frame)
        elapsed_ms = (time.perf_counter() - start) * 1000
        if index > 0:
            timings.append(elapsed_ms)
            sizes.append(len(encoded))
    ordered = sorted(timings)
    median_ms = statistics.median(timings)
    return {
        "frames": frames,
        "encode_ms": {
            "median": median_ms,
            "p95": ordered[max(0, int(len(ordered) * 0.95) - 1)],
            "max": max(timings),
        },
        "encoded_bytes": {
            "median": int(statistics.median(sizes)),
            "max": max(sizes),
        },
        "encode_only_fps": 1000 / median_ms,
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--frames", type=int, default=12)
    args = parser.parse_args()

    encoders: dict[str, Encoder] = {
        "kitty-zlib-rgba": _kitty_zlib,
        "kitty-png": _kitty_png,
        "iterm-png": _iterm_png,
    }
    tracemalloc.start()
    results = {
        pattern: {
            name: _measure(
                encoder,
                width=args.width,
                height=args.height,
                pattern=pattern,
                frames=args.frames,
            )
            for name, encoder in encoders.items()
        }
        for pattern in ("opaque", "alpha-heavy", "high-change")
    }
    _, peak = tracemalloc.get_traced_memory()
    print(
        json.dumps(
            {
                "resolution": [args.width, args.height],
                "frames_per_case": args.frames,
                "peak_traced_memory_bytes": peak,
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
