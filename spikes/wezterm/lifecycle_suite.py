"""Run terminal restoration cases in disposable WezTerm panes."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import uuid
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


def _pane(pane_id: int) -> dict[str, Any]:
    for pane in _panes():
        if pane.get("pane_id") == pane_id:
            return pane
    raise LookupError(f"pane {pane_id} not found")


def _size(pane_id: int) -> dict[str, int]:
    return {key: int(value) for key, value in _pane(pane_id)["size"].items()}


def _restore_parent_width(pane_id: int, target_cols: int) -> dict[str, int]:
    current = _size(pane_id)
    delta = target_cols - current["cols"]
    if delta > 0:
        _run(
            "wezterm",
            "cli",
            "adjust-pane-size",
            "--pane-id",
            str(pane_id),
            "--amount",
            str(delta),
            "Right",
        )
    return _size(pane_id)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent-pane-id", type=int, required=True)
    parser.add_argument("--font", type=Path, required=True)
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--results-dir", type=Path, required=True)
    args = parser.parse_args()

    host_script = Path(__file__).with_name("lifecycle_host.py")
    parent_before = _size(args.parent_pane_id)
    cases: list[dict[str, Any]] = []

    for case_name in ("normal", "failure", "interrupt"):
        token = uuid.uuid4().hex
        live_result_path = args.results_dir / f"lifecycle-{case_name}-{token}.json"
        host_result_path = live_result_path.with_suffix(".host.json")
        child_id: int | None = None
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
                    "--",
                    sys.executable,
                    str(host_script),
                    "--font",
                    str(args.font),
                    "--result",
                    str(live_result_path),
                    "--case",
                    case_name,
                    "--hold-seconds",
                    "30",
                )
            )
            for _ in range(200):
                if host_result_path.is_file():
                    break
                time.sleep(0.05)
            else:
                raise TimeoutError(f"host marker not created for {case_name}")

            pane = _pane(child_id)
            visible_text = _run("wezterm", "cli", "get-text", "--pane-id", str(child_id))
            live_result = json.loads(live_result_path.read_text(encoding="utf-8"))
            host_result = json.loads(host_result_path.read_text(encoding="utf-8"))
            expected_status = {
                "normal": "completed",
                "failure": "failed",
                "interrupt": "interrupted",
            }[case_name]
            cases.append(
                {
                    "case": case_name,
                    "pane_id": child_id,
                    "cursor_visibility": pane.get("cursor_visibility"),
                    "primary_screen_marker_visible": "PHASE0_LIFECYCLE_READY" in visible_text,
                    "live_status": live_result.get("status"),
                    "expected_live_status": expected_status,
                    "child_returncode": host_result.get("child_returncode"),
                    "passed": (
                        pane.get("cursor_visibility") == "Visible"
                        and "PHASE0_LIFECYCLE_READY" in visible_text
                        and live_result.get("status") == expected_status
                    ),
                }
            )
        except Exception as error:
            cases.append(
                {
                    "case": case_name,
                    "pane_id": child_id,
                    "passed": False,
                    "error": f"{type(error).__name__}: {error}",
                }
            )
        finally:
            if child_id is not None:
                try:
                    _run("wezterm", "cli", "kill-pane", "--pane-id", str(child_id))
                except Exception:
                    pass
            time.sleep(0.2)

    parent_after_cleanup = _size(args.parent_pane_id)
    parent_after_restore = _restore_parent_width(args.parent_pane_id, parent_before["cols"])
    result = {
        "parent_pane_id": args.parent_pane_id,
        "parent_before": parent_before,
        "parent_after_cleanup": parent_after_cleanup,
        "parent_after_restore": parent_after_restore,
        "cases": cases,
        "passed": all(case["passed"] for case in cases),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
