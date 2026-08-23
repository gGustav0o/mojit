"""Keep an acceptance controller alive while the installed CLI receives real Ctrl+C."""

from __future__ import annotations

import argparse
import signal
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--command", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    arguments = parser.parse_args()

    signal.signal(signal.SIGINT, lambda _signum, _frame: None)
    process = subprocess.Popen(
        (str(arguments.command), "\u96fb\u8133\u4e16\u754c", "--effect", "neon")
    )
    return_code = process.wait()
    arguments.result.write_text(f"{return_code}\n", encoding="ascii")
    print(f"MOJIT_INSTALLED_INTERRUPT_EXIT={return_code}")
    input("Interrupt acceptance complete; pane may be closed: ")
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
