"""Orchestrate the five-minute Phase 0 proof in an isolated WezTerm window."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def _run(*command: str, timeout: float = 8) -> str:
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
    )
    return completed.stdout.strip()


def _panes() -> list[dict[str, Any]]:
    return json.loads(_run("wezterm", "cli", "list", "--format", "json"))


def _pane(pane_id: int) -> dict[str, Any] | None:
    return next((pane for pane in _panes() if pane.get("pane_id") == pane_id), None)


def _size(pane_id: int) -> dict[str, int] | None:
    pane = _pane(pane_id)
    if pane is None:
        return None
    return {key: int(value) for key, value in pane["size"].items()}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-pane-id", type=int, required=True)
    parser.add_argument("--font", type=Path, required=True)
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--duration", type=float, default=300)
    parser.add_argument("--fps", type=int, default=30)
    args = parser.parse_args()

    live_script = Path(__file__).with_name("live_proof.py")
    live_id: int | None = None
    auxiliary_id: int | None = None
    resize_observations: list[dict[str, Any]] = []
    orchestration_error: str | None = None
    started = time.perf_counter()
    try:
        live_id = int(
            _run(
                "wezterm",
                "cli",
                "spawn",
                "--pane-id",
                str(args.source_pane_id),
                "--new-window",
                "--workspace",
                "mojit-phase0",
                "--cwd",
                str(args.cwd.resolve()),
                "--",
                sys.executable,
                str(live_script),
                "--font",
                str(args.font),
                "--duration",
                str(args.duration),
                "--fps",
                str(args.fps),
                "--protocol",
                "kitty-png",
                "--vertical",
                "--result",
                str(args.result.resolve()),
                "--restore-twice",
            )
        )
        time.sleep(5)
        resize_observations.append({"stage": "initial", "size": _size(live_id)})

        auxiliary_id = int(
            _run(
                "wezterm",
                "cli",
                "split-pane",
                "--pane-id",
                str(live_id),
                "--right",
                "--percent",
                "20",
                "--cwd",
                str(args.cwd.resolve()),
            )
        )
        time.sleep(1)
        resize_observations.append({"stage": "split", "size": _size(live_id)})
        for index in range(10):
            direction = "Left" if index % 2 else "Right"
            _run(
                "wezterm",
                "cli",
                "adjust-pane-size",
                "--pane-id",
                str(auxiliary_id),
                "--amount",
                "1",
                direction,
            )
            time.sleep(0.15)
            resize_observations.append({"stage": f"transition-{index + 1}", "size": _size(live_id)})
        _run("wezterm", "cli", "kill-pane", "--pane-id", str(auxiliary_id))
        auxiliary_id = None
        time.sleep(1)
        resize_observations.append({"stage": "auxiliary-closed", "size": _size(live_id)})

        timeout_at = started + args.duration + 45
        while not args.result.is_file() and time.perf_counter() < timeout_at:
            time.sleep(0.25)
        if not args.result.is_file():
            raise TimeoutError("integrated proof did not produce its result")
    except Exception as error:
        orchestration_error = f"{type(error).__name__}: {error}"
    finally:
        if auxiliary_id is not None:
            try:
                _run("wezterm", "cli", "kill-pane", "--pane-id", str(auxiliary_id))
            except Exception:
                pass
        if orchestration_error is not None and live_id is not None and _pane(live_id) is not None:
            try:
                _run("wezterm", "cli", "kill-pane", "--pane-id", str(live_id))
            except Exception:
                pass

    live_result = (
        json.loads(args.result.read_text(encoding="utf-8")) if args.result.is_file() else None
    )
    period_ms = 1000 / args.fps
    passed = bool(
        orchestration_error is None
        and live_result
        and live_result.get("status") == "completed"
        and live_result.get("resize_count", 0) >= 2
        and live_result.get("achieved_fps", 0) >= args.fps * 0.95
        and live_result.get("frame_ms", {}).get("p95", period_ms + 1) < period_ms
    )
    result = {
        "passed": passed,
        "orchestration_error": orchestration_error,
        "live_pane_id": live_id,
        "requested_duration_seconds": args.duration,
        "requested_fps": args.fps,
        "resize_observations": resize_observations,
        "live_result": live_result,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
