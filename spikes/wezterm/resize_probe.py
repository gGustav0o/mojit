"""Exercise repeated WezTerm pane resize transitions in a disposable split."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def _run(*command: str, timeout: float = 5) -> str:
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


def _pane(pane_id: int) -> dict[str, Any]:
    for pane in _panes():
        if pane.get("pane_id") == pane_id:
            return pane
    raise LookupError(f"pane {pane_id} not found")


def _size(pane_id: int) -> dict[str, int]:
    size = _pane(pane_id)["size"]
    return {key: int(size[key]) for key in ("rows", "cols", "pixel_width", "pixel_height", "dpi")}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent-pane-id", type=int, required=True)
    parser.add_argument("--transitions", type=int, default=20)
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    args = parser.parse_args()

    parent_before = _size(args.parent_pane_id)
    child_id: int | None = None
    observations: list[dict[str, Any]] = []
    error: str | None = None
    try:
        child_id = int(
            _run(
                "wezterm",
                "cli",
                "split-pane",
                "--pane-id",
                str(args.parent_pane_id),
                "--right",
                "--percent",
                "25",
                "--cwd",
                str(args.cwd.resolve()),
            )
        )
        observations.append({"transition": 0, "child_size": _size(child_id)})
        for index in range(1, args.transitions + 1):
            direction = "Left" if index % 2 else "Right"
            _run(
                "wezterm",
                "cli",
                "adjust-pane-size",
                "--pane-id",
                str(child_id),
                "--amount",
                "1",
                direction,
            )
            time.sleep(0.05)
            observations.append(
                {
                    "transition": index,
                    "direction": direction,
                    "child_size": _size(child_id),
                }
            )
    except Exception as caught:
        error = f"{type(caught).__name__}: {caught}"
    finally:
        if child_id is not None:
            try:
                _run("wezterm", "cli", "kill-pane", "--pane-id", str(child_id))
            except Exception as cleanup_error:
                error = error or f"cleanup failed: {cleanup_error}"
        time.sleep(0.2)

    parent_after = _size(args.parent_pane_id)
    unique_sizes = list(
        {
            json.dumps(item["child_size"], sort_keys=True): item["child_size"]
            for item in observations
        }.values()
    )
    result = {
        "parent_pane_id": args.parent_pane_id,
        "child_pane_id": child_id,
        "requested_transitions": args.transitions,
        "completed_transitions": max(0, len(observations) - 1),
        "parent_before": parent_before,
        "parent_after": parent_after,
        "parent_restored": parent_before == parent_after,
        "unique_child_sizes": unique_sizes,
        "observations": observations,
        "error": error,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if error is None and parent_before == parent_after else 1


if __name__ == "__main__":
    raise SystemExit(main())
