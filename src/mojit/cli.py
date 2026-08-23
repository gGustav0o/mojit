"""Command-line composition root.

Argument parsing, stdin resolution, dependency assembly, and user-facing error
reporting will live here. Product behavior starts after Phase 0.
"""

import sys


def main() -> int:
    """Report that the product runtime has not been implemented yet."""
    print("mojit: Phase 0 is complete; product runtime is not implemented", file=sys.stderr)
    return 2
