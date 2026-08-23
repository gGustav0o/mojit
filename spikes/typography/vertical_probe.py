"""Measure Pillow/Raqm horizontal and vertical Japanese rasterization."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, features

CORPUS = (
    "電脳世界",
    "警告、「猫」。",
    "スーパー（電脳）『世界』",
)


def _render(
    text: str,
    font_path: Path,
    font_size: int,
    direction: str,
    output: Path | None,
) -> dict[str, Any]:
    font = ImageFont.truetype(
        str(font_path),
        font_size,
        layout_engine=ImageFont.Layout.RAQM,
    )
    probe = Image.new("L", (1, 1), 0)
    draw = ImageDraw.Draw(probe)
    bbox = draw.textbbox((0, 0), text, font=font, direction=direction, language="ja")
    left, top, right, bottom = bbox
    padding = 8
    image = Image.new("L", (right - left + padding * 2, bottom - top + padding * 2), 0)
    draw = ImageDraw.Draw(image)
    draw.text(
        (padding - left, padding - top),
        text,
        fill=255,
        font=font,
        direction=direction,
        language="ja",
    )
    content_bbox = image.getbbox()
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        image.save(output)
    return {
        "text": text,
        "direction": direction,
        "font_size": font_size,
        "textbbox": bbox,
        "image_size": image.size,
        "content_bbox": content_bbox,
        "alpha_sha256": hashlib.sha256(image.tobytes()).hexdigest(),
        "output": str(output) if output else None,
    }


def _benchmark(font_path: Path, direction: str, iterations: int) -> dict[str, Any]:
    samples: list[float] = []
    for index in range(iterations + 2):
        start = time.perf_counter()
        _render(CORPUS[index % len(CORPUS)], font_path, 128, direction, None)
        elapsed_ms = (time.perf_counter() - start) * 1000
        if index >= 2:
            samples.append(elapsed_ms)
    ordered = sorted(samples)
    return {
        "iterations": iterations,
        "median_ms": statistics.median(samples),
        "p95_ms": ordered[max(0, int(len(ordered) * 0.95) - 1)],
        "max_ms": max(samples),
    }


def _basic_engine_ttb(font_path: Path) -> dict[str, Any]:
    try:
        font = ImageFont.truetype(
            str(font_path),
            64,
            layout_engine=ImageFont.Layout.BASIC,
        )
        draw = ImageDraw.Draw(Image.new("L", (512, 512), 0))
        draw.textbbox((0, 0), CORPUS[0], font=font, direction="ttb", language="ja")
    except Exception as error:  # The exception type is Pillow-version-specific.
        return {"supported": False, "error_type": type(error).__name__, "error": str(error)}
    return {"supported": True, "error_type": None, "error": None}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--font", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=20)
    args = parser.parse_args()

    if not args.font.is_file():
        parser.error(f"font does not exist: {args.font}")
    if not features.check_feature("raqm"):
        parser.error("Pillow Raqm support is unavailable")

    rendered: list[dict[str, Any]] = []
    for direction in ("ltr", "ttb"):
        for index, text in enumerate(CORPUS, start=1):
            rendered.append(
                _render(
                    text,
                    args.font,
                    128,
                    direction,
                    args.output_dir / f"{direction}-{index}.png",
                )
            )

    repeat_a = _render(CORPUS[1], args.font, 128, "ttb", None)
    repeat_b = _render(CORPUS[1], args.font, 128, "ttb", None)
    result = {
        "font": str(args.font.resolve()),
        "font_sha256": hashlib.sha256(args.font.read_bytes()).hexdigest(),
        "pillow_features": {
            "raqm": features.check_feature("raqm"),
            "raqm_version": features.version_feature("raqm"),
            "freetype_version": features.version_module("freetype2"),
        },
        "rendered": rendered,
        "deterministic_repeat": repeat_a["alpha_sha256"] == repeat_b["alpha_sha256"],
        "basic_engine_ttb": _basic_engine_ttb(args.font),
        "benchmark": {
            direction: _benchmark(args.font, direction, args.iterations)
            for direction in ("ltr", "ttb")
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
