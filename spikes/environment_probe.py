"""Collect the reproducible Phase 0 environment baseline as JSON."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy
from PIL import __version__ as pillow_version
from PIL import features


def _run(*command: str) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"command": list(command), "error": str(error)}
    return {
        "command": list(command),
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def _font(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"path": str(path), "available": False}
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "path": str(path),
        "available": True,
        "size_bytes": path.stat().st_size,
        "sha256": digest,
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--font",
        action="append",
        default=[],
        help="Font path to fingerprint; may be repeated",
    )
    args = parser.parse_args()

    font_paths = args.font or [
        r"C:\Windows\Fonts\YuGothB.ttc",
        r"C:\Windows\Fonts\YuGothM.ttc",
        r"C:\Windows\Fonts\meiryo.ttc",
        r"C:\Windows\Fonts\msgothic.ttc",
    ]
    result = {
        "platform": platform.platform(),
        "python": {
            "version": platform.python_version(),
            "executable": sys.executable,
        },
        "cpu": {
            "processor_identifier": os.environ.get("PROCESSOR_IDENTIFIER"),
            "logical_processors": os.cpu_count(),
        },
        "libraries": {
            "numpy": numpy.__version__,
            "pillow": pillow_version,
            "raqm": features.check_feature("raqm"),
            "raqm_version": features.version_feature("raqm"),
            "freetype_version": features.version_module("freetype2"),
        },
        "terminal_environment": {
            key: os.environ.get(key)
            for key in (
                "TERM",
                "TERM_PROGRAM",
                "TERM_PROGRAM_VERSION",
                "WEZTERM_PANE",
                "WEZTERM_UNIX_SOCKET",
            )
        },
        "wezterm_version": _run("wezterm", "--version"),
        "wezterm_panes": _run("wezterm", "cli", "list", "--format", "json"),
        "fonts": [_font(Path(path)) for path in font_paths],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
