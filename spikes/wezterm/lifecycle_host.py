"""Keep a disposable pane alive after a live proof for external state inspection."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--font", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--case", choices=("normal", "failure", "interrupt"), required=True)
    parser.add_argument("--hold-seconds", type=float, default=20)
    args = parser.parse_args()

    live_proof = Path(__file__).with_name("live_proof.py")
    command = [
        sys.executable,
        str(live_proof),
        "--font",
        str(args.font),
        "--duration",
        "2",
        "--fps",
        "10",
        "--protocol",
        "kitty-png",
        "--result",
        str(args.result),
        "--restore-twice",
    ]
    if args.case == "failure":
        command.extend(("--fail-after", "5"))
    elif args.case == "interrupt":
        command.extend(("--interrupt-after", "5"))

    completed = subprocess.run(command, check=False)
    host_result = {
        "case": args.case,
        "child_returncode": completed.returncode,
        "live_result": str(args.result),
    }
    marker = args.result.with_suffix(".host.json")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps(host_result, indent=2), encoding="utf-8")
    print(f"PHASE0_LIFECYCLE_READY case={args.case} returncode={completed.returncode}", flush=True)
    time.sleep(args.hold_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
