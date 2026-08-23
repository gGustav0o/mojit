"""Bounded exact-pane geometry acquisition through the WezTerm CLI socket."""

from __future__ import annotations

import json
import math
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from numbers import Real

from mojit.adapters.wezterm.errors import ViewportQueryError, WezTermPreflightError
from mojit.core.models import Viewport

WEZTERM_LIST_COMMAND = ("wezterm", "cli", "list", "--format", "json")
VIEWPORT_TIMEOUT_SECONDS = 2.0
MAX_STDOUT_BYTES = 1024 * 1024
MAX_STDERR_EXCERPT_BYTES = 4096


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Bounded subprocess values consumed by the pure response parser."""

    returncode: int
    stdout: bytes
    stderr: bytes


@dataclass(frozen=True, slots=True)
class PaneGeometry:
    """Validated pixel layout and cell placement geometry for one pane."""

    pane_id: int
    viewport: Viewport
    columns: int
    rows: int
    dpi: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "pane_id", _require_int(self.pane_id, name="pane_id", minimum=0))
        if not isinstance(self.viewport, Viewport):
            raise ViewportQueryError("viewport must be a Viewport")
        object.__setattr__(self, "columns", _require_int(self.columns, name="columns"))
        object.__setattr__(self, "rows", _require_int(self.rows, name="rows"))
        if self.dpi is not None:
            if isinstance(self.dpi, bool) or not isinstance(self.dpi, Real):
                raise ViewportQueryError("dpi must be a real number or None")
            converted = float(self.dpi)
            if not math.isfinite(converted) or converted <= 0.0:
                raise ViewportQueryError("dpi must be finite and positive")
            object.__setattr__(self, "dpi", converted)


Runner = Callable[[tuple[str, ...], float], CommandResult]


def _require_int(value: object, *, name: str, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ViewportQueryError(f"{name} must be an integer")
    if value < minimum:
        raise ViewportQueryError(f"{name} must be >= {minimum}")
    return value


def _normalize_reported_dpi(value: object) -> float | None:
    """Map WezTerm's zero unknown-DPI sentinel to the model's ``None``."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ViewportQueryError("dpi must be a real number or None")
    converted = float(value)
    if converted == 0.0:
        return None
    if not math.isfinite(converted) or converted < 0.0:
        raise ViewportQueryError("dpi must be finite and non-negative")
    return converted


def parse_pane_id(environ: Mapping[str, str]) -> int:
    """Read one strict decimal pane ID without consulting process globals."""
    raw = environ.get("WEZTERM_PANE")
    if raw is None:
        raise WezTermPreflightError("WEZTERM_PANE is required; run mojit inside WezTerm")
    if not isinstance(raw, str) or not raw or not raw.isascii() or not raw.isdecimal():
        raise WezTermPreflightError("WEZTERM_PANE must be a non-negative decimal integer")
    return int(raw, 10)


def parse_pane_geometry(document: str, pane_id: int) -> PaneGeometry:
    """Parse one exact target from a decoded WezTerm pane-list document."""
    target_id = _require_int(pane_id, name="pane_id", minimum=0)
    if not isinstance(document, str):
        raise TypeError("document must be a string")
    try:
        root = json.loads(document)
    except json.JSONDecodeError as error:
        raise ViewportQueryError(f"wezterm cli returned invalid JSON: {error.msg}") from error
    if not isinstance(root, list):
        raise ViewportQueryError("wezterm cli JSON root must be a list")

    matches = [
        pane
        for pane in root
        if isinstance(pane, dict)
        and isinstance(pane.get("pane_id"), int)
        and not isinstance(pane.get("pane_id"), bool)
        and pane["pane_id"] == target_id
    ]
    if not matches:
        raise ViewportQueryError(f"pane {target_id} was not returned by wezterm cli")
    if len(matches) != 1:
        raise ViewportQueryError(f"pane {target_id} was returned more than once")

    size = matches[0].get("size")
    if not isinstance(size, dict):
        raise ViewportQueryError(f"pane {target_id} size must be an object")
    width = _require_int(size.get("pixel_width"), name="pixel_width")
    height = _require_int(size.get("pixel_height"), name="pixel_height")
    columns = _require_int(size.get("cols"), name="cols")
    rows = _require_int(size.get("rows"), name="rows")
    dpi = _normalize_reported_dpi(size.get("dpi"))
    return PaneGeometry(
        pane_id=target_id,
        viewport=Viewport(width, height),
        columns=columns,
        rows=rows,
        dpi=dpi,
    )


def run_wezterm_cli(command: tuple[str, ...], timeout_seconds: float) -> CommandResult:
    """Run one no-shell, no-stdin WezTerm CLI command with a hard timeout."""
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
            creationflags=creation_flags,
        )
    except subprocess.TimeoutExpired as error:
        raise ViewportQueryError(
            f"wezterm cli timed out after {timeout_seconds:g} seconds"
        ) from error
    except FileNotFoundError as error:
        raise ViewportQueryError("wezterm executable was not found") from error
    except OSError as error:
        raise ViewportQueryError(f"wezterm cli could not start: {error}") from error
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def _stderr_excerpt(value: bytes) -> str:
    excerpt = value[:MAX_STDERR_EXCERPT_BYTES].decode("utf-8", errors="replace").strip()
    return excerpt or "no stderr output"


def query_pane_geometry(
    pane_id: int,
    *,
    runner: Runner = run_wezterm_cli,
) -> PaneGeometry:
    """Acquire and validate the current geometry for exactly one target pane."""
    target_id = _require_int(pane_id, name="pane_id", minimum=0)
    result = runner(WEZTERM_LIST_COMMAND, VIEWPORT_TIMEOUT_SECONDS)
    if not isinstance(result, CommandResult):
        raise TypeError("runner must return CommandResult")
    if isinstance(result.returncode, bool) or not isinstance(result.returncode, int):
        raise ViewportQueryError("wezterm cli return code must be an integer")
    if not isinstance(result.stdout, bytes) or not isinstance(result.stderr, bytes):
        raise ViewportQueryError("wezterm cli output must be bytes")
    if result.returncode != 0:
        raise ViewportQueryError(
            f"wezterm cli failed with exit code {result.returncode}: "
            f"{_stderr_excerpt(result.stderr)}"
        )
    if len(result.stdout) > MAX_STDOUT_BYTES:
        raise ViewportQueryError("wezterm cli output exceeds 1 MiB")
    try:
        document = result.stdout.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ViewportQueryError("wezterm cli output is not valid UTF-8") from error
    return parse_pane_geometry(document, target_id)
