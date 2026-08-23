"""Live Phase 0 proof for rendering, resize, transport, and cleanup."""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import statistics
import subprocess
import sys
import time
import zlib
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont, features
from protocol import (
    begin_synchronized_update,
    end_synchronized_update,
    enter_terminal,
    iterm_image,
    kitty_image,
    restore_terminal,
)

IMAGE_ID = 0x4D4F4A


def _pane(pane_id: int) -> dict[str, Any]:
    completed = subprocess.run(
        ("wezterm", "cli", "list", "--format", "json"),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=2,
    )
    for pane in json.loads(completed.stdout):
        if pane.get("pane_id") == pane_id:
            return pane
    raise LookupError(f"pane {pane_id} not found")


def _mask(text: str, font_path: Path, viewport: tuple[int, int], vertical: bool) -> np.ndarray:
    width, height = viewport
    direction = "ttb" if vertical else "ltr"
    font_size = max(8, min(width, height) // 5)
    font = ImageFont.truetype(
        str(font_path),
        font_size,
        layout_engine=ImageFont.Layout.RAQM,
    )
    image = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(image)
    left, top, right, bottom = draw.textbbox(
        (0, 0), text, font=font, direction=direction, language="ja"
    )
    x = (width - (right - left)) // 2 - left
    y = (height - (bottom - top)) // 2 - top
    draw.text(
        (x, y),
        text,
        fill=255,
        font=font,
        direction=direction,
        language="ja",
    )
    return np.asarray(image, dtype=np.uint8)


def _frame(mask: np.ndarray, frame_index: int, fps: int) -> np.ndarray:
    phase = frame_index / fps
    intensity = 0.55 + 0.45 * math.sin(phase * math.tau)
    rgba = np.zeros((*mask.shape, 4), dtype=np.uint8)
    rgba[..., 0] = np.uint8(32 * intensity)
    rgba[..., 1] = np.uint8(220 * intensity)
    rgba[..., 2] = np.uint8(255 * intensity)
    rgba[..., 3] = mask
    return rgba


def _png(frame: np.ndarray) -> bytes:
    stream = io.BytesIO()
    Image.fromarray(frame, mode="RGBA").save(stream, format="PNG", compress_level=1)
    return stream.getvalue()


def _encode(frame: np.ndarray, protocol: str, columns: int, rows: int) -> bytes:
    height, width, _ = frame.shape
    if protocol == "kitty-zlib-rgba":
        return kitty_image(
            zlib.compress(frame.tobytes(), level=1),
            image_id=IMAGE_ID,
            image_format=32,
            width=width,
            height=height,
            compressed=True,
            columns=columns,
            rows=rows,
        )
    if protocol == "kitty-png":
        return kitty_image(
            _png(frame),
            image_id=IMAGE_ID,
            image_format=100,
            width=width,
            height=height,
            compressed=False,
            columns=columns,
            rows=rows,
        )
    if protocol == "iterm-png":
        return iterm_image(_png(frame))
    raise ValueError(f"unsupported protocol: {protocol}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("text", nargs="?", default="電脳世界")
    parser.add_argument("--font", type=Path, required=True)
    parser.add_argument("--duration", type=float, default=30)
    parser.add_argument("--fps", type=int, default=15)
    parser.add_argument(
        "--protocol",
        choices=("kitty-zlib-rgba", "kitty-png", "iterm-png"),
        default="kitty-zlib-rgba",
    )
    parser.add_argument("--vertical", action="store_true")
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--fail-after", type=int)
    parser.add_argument("--interrupt-after", type=int)
    parser.add_argument("--restore-twice", action="store_true")
    args = parser.parse_args()

    if not features.check_feature("raqm"):
        parser.error("Pillow Raqm support is unavailable")
    pane_id = int(os.environ["WEZTERM_PANE"])
    stdout = sys.stdout.buffer
    frame_index = 0
    resize_count = 0
    timings: list[float] = []
    bytes_written = 0
    status = "completed"
    error: str | None = None
    current_size: tuple[int, int, int, int] | None = None
    mask: np.ndarray | None = None
    started = time.perf_counter()
    deadline = started
    next_viewport_check = started

    stdout.write(enter_terminal())
    stdout.flush()
    try:
        while time.perf_counter() - started < args.duration:
            now = time.perf_counter()
            if now >= next_viewport_check or current_size is None:
                pane = _pane(pane_id)
                size = pane["size"]
                observed = (
                    int(size["pixel_width"]),
                    int(size["pixel_height"]),
                    int(size["cols"]),
                    int(size["rows"]),
                )
                if observed != current_size:
                    if current_size is not None:
                        resize_count += 1
                    current_size = observed
                    mask = _mask(args.text, args.font, observed[:2], args.vertical)
                next_viewport_check = now + 0.25

            assert current_size is not None and mask is not None
            frame_started = time.perf_counter()
            frame = _frame(mask, frame_index, args.fps)
            encoded = _encode(frame, args.protocol, current_size[2], current_size[3])
            stdout.write(begin_synchronized_update())
            stdout.write(b"\x1b[H")
            stdout.write(encoded)
            stdout.write(end_synchronized_update())
            stdout.flush()
            timings.append((time.perf_counter() - frame_started) * 1000)
            bytes_written += len(encoded)
            frame_index += 1

            if args.fail_after is not None and frame_index >= args.fail_after:
                raise RuntimeError("injected Phase 0 failure")
            if args.interrupt_after is not None and frame_index >= args.interrupt_after:
                raise KeyboardInterrupt

            deadline = started + frame_index / args.fps
            remaining = deadline - time.perf_counter()
            if remaining > 0:
                time.sleep(remaining)
    except KeyboardInterrupt:
        status = "interrupted"
    except Exception as caught:
        status = "failed"
        error = f"{type(caught).__name__}: {caught}"
    finally:
        stdout.write(restore_terminal(IMAGE_ID))
        if args.restore_twice:
            stdout.write(restore_terminal(IMAGE_ID))
        stdout.flush()
        elapsed = time.perf_counter() - started
        ordered = sorted(timings)
        result = {
            "status": status,
            "error": error,
            "pane_id": pane_id,
            "protocol": args.protocol,
            "vertical": args.vertical,
            "requested_duration_seconds": args.duration,
            "elapsed_seconds": elapsed,
            "requested_fps": args.fps,
            "frames": frame_index,
            "achieved_fps": frame_index / elapsed if elapsed else 0,
            "resize_count": resize_count,
            "final_viewport": current_size,
            "bytes_written": bytes_written,
            "frame_ms": {
                "median": statistics.median(timings) if timings else None,
                "p95": ordered[max(0, int(len(ordered) * 0.95) - 1)] if ordered else None,
                "max": max(timings) if timings else None,
            },
        }
        args.result.parent.mkdir(parents=True, exist_ok=True)
        args.result.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0 if status in {"completed", "interrupted"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
