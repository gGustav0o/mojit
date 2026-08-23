"""Measure WezTerm pixel viewport discovery and stdin isolation."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from typing import Any


def _list_panes(timeout_seconds: float) -> tuple[list[dict[str, Any]], float]:
    start = time.perf_counter()
    completed = subprocess.run(
        ("wezterm", "cli", "list", "--format", "json"),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout_seconds,
    )
    elapsed_ms = (time.perf_counter() - start) * 1000
    return json.loads(completed.stdout), elapsed_ms


def _select(panes: list[dict[str, Any]], pane_id: int) -> dict[str, Any]:
    for pane in panes:
        if pane.get("pane_id") == pane_id:
            return pane
    raise LookupError(f"pane {pane_id} was not returned by wezterm cli list")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--pane-id", type=int)
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument("--consume-stdin", action="store_true")
    args = parser.parse_args()

    pane_id = args.pane_id
    if pane_id is None:
        raw_pane_id = os.environ.get("WEZTERM_PANE")
        if raw_pane_id is None:
            parser.error("--pane-id or WEZTERM_PANE is required")
        pane_id = int(raw_pane_id)

    consumed = None
    if args.consume_stdin:
        if not sys.stdin.isatty():
            sys.stdin.reconfigure(encoding="utf-8")
        consumed = sys.stdin.read()

    samples: list[float] = []
    observations: list[dict[str, Any]] = []
    for _ in range(args.iterations):
        panes, latency_ms = _list_panes(args.timeout)
        pane = _select(panes, pane_id)
        size = pane.get("size", {})
        required = ("rows", "cols", "pixel_width", "pixel_height", "dpi")
        missing = [key for key in required if key not in size]
        if missing:
            raise RuntimeError(f"WezTerm size object lacks fields: {missing}")
        samples.append(latency_ms)
        observations.append({key: size[key] for key in required})

    ordered = sorted(samples)
    unique = list({json.dumps(item, sort_keys=True): item for item in observations}.values())
    result = {
        "pane_id": pane_id,
        "stdin": {
            "consumed": args.consume_stdin,
            "text": consumed,
            "isatty_after_read": sys.stdin.isatty(),
        },
        "iterations": args.iterations,
        "latency_ms": {
            "median": statistics.median(samples),
            "p95": ordered[max(0, int(len(ordered) * 0.95) - 1)],
            "max": max(samples),
        },
        "unique_viewports": unique,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
