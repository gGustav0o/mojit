"""Single production entry point: activate native runtime, then import the CLI."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from mojit.native_runtime import NativeRuntimeError, activate_native_runtime


def main(argv: Sequence[str] | None = None) -> int:
    """Start mojit after deterministic native dependency activation."""
    try:
        activate_native_runtime()
    except NativeRuntimeError as error:
        print(f"mojit: {error}", file=sys.stderr)
        return 2

    from mojit.cli import main as cli_main

    return cli_main(argv)
