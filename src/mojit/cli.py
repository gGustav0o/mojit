"""Command-line parsing and pre-terminal composition root."""

from __future__ import annotations

import argparse
import os
import sys
import traceback
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from functools import partial
from pathlib import Path
from typing import BinaryIO, TextIO, cast

from mojit.adapters.budoux_segmenter import (
    JapaneseSegmentationError,
    segment_japanese_phrases,
)
from mojit.adapters.clock import SystemMonotonicClock
from mojit.adapters.config_file import ConfigFileError, load_config_document
from mojit.adapters.font_resource import FontResourceError, load_font_resource
from mojit.adapters.wezterm.backend import WezTermBackend
from mojit.adapters.wezterm.errors import WezTermPreflightError
from mojit.application.input_text import InputTextError, resolve_input_text
from mojit.application.request import PreparedRun
from mojit.application.runtime import Rasterizer, run_animation
from mojit.config.models import (
    DEFAULT_EFFECT,
    DEFAULT_FONT,
    DEFAULT_FPS,
    DEFAULT_MARGIN,
    DEFAULT_ORIENTATION,
    DEFAULT_SEED,
    MAX_FPS,
    MIN_FPS,
    ConfigOverrides,
    ConfigValidationError,
)
from mojit.config.resolve import resolve_config
from mojit.config.toml import ConfigSyntaxError, parse_toml_config
from mojit.core.models import Orientation
from mojit.core.typography import (
    ShapingUnavailableError,
    rasterize_text_mask,
    require_shaping_capability,
)
from mojit.effects.registry import UnknownEffectError, effect_names, get_effect
from mojit.scenes.presets import UnknownSceneError, get_scene_builder, scene_names


class CliUsageError(ValueError):
    """Command-line arguments violate the CLI contract."""


class LifecycleFailure(RuntimeError):
    """Terminal cleanup failed, optionally alongside a primary runtime failure."""

    def __init__(self, primary: BaseException | None, cleanup: BaseException) -> None:
        self.primary = primary
        self.cleanup = cleanup
        cleanup_text = f"{type(cleanup).__name__}: {cleanup}"
        if primary is None:
            message = f"terminal cleanup failed ({cleanup_text})"
        else:
            primary_text = f"{type(primary).__name__}: {primary}"
            message = (
                f"runtime failed ({primary_text}); terminal cleanup also failed ({cleanup_text})"
            )
        super().__init__(message)


class _CliExit(Exception):
    def __init__(self, status: int) -> None:
        self.status = status


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CliUsageError(message)

    def exit(self, status: int = 0, message: str | None = None) -> None:
        if message:
            self._print_message(message, sys.stderr)
        if status == 0:
            raise _CliExit(status)
        raise CliUsageError(message or "invalid command line")


class CommandMode(str, Enum):
    RUN = "run"
    LIST_EFFECTS = "list-effects"
    LIST_SCENES = "list-scenes"


@dataclass(frozen=True, slots=True)
class ParsedCli:
    mode: CommandMode
    text: str | None
    config_path: str | None
    overrides: ConfigOverrides
    debug: bool


_HELP_EPILOG = """\
Input:
  Supply TEXT as one Unicode line. When TEXT is omitted, mojit reads UTF-8 text
  from stdin. Stdin is reserved for text and cannot be used as --config -.

Configuration precedence:
  command line > --config PATH > %APPDATA%\\mojit\\config.toml > built-in defaults

Examples:
  mojit "hello"
  mojit "warning" --effect glitch --fps 15
  mojit "hello" --vertical
  "piped text" | mojit
  mojit --list-effects
  mojit --list-scenes
  mojit "rain" --scene rainy-night

Exit status:
  0  success, help, or normal Ctrl+C termination
  1  unexpected runtime or terminal-cleanup failure
  2  invalid input, configuration, environment, or command line
"""


def _parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(
        prog="mojit",
        description="Display large animated Unicode text in WezTerm.",
        epilog=_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "text",
        nargs="?",
        metavar="TEXT",
        help="Unicode text to display; read UTF-8 stdin when omitted",
    )
    parser.add_argument(
        "-e",
        "--effect",
        metavar="ID",
        help=f"animation effect ({', '.join(effect_names())}; default: {DEFAULT_EFFECT})",
    )
    orientation = parser.add_mutually_exclusive_group()
    orientation.add_argument(
        "--vertical",
        dest="orientation",
        action="store_const",
        const=Orientation.VERTICAL,
        help="lay out text top-to-bottom",
    )
    orientation.add_argument(
        "--horizontal",
        dest="orientation",
        action="store_const",
        const=Orientation.HORIZONTAL,
        help=(
            f"lay out text left-to-right and override config (default: {DEFAULT_ORIENTATION.value})"
        ),
    )
    parser.add_argument(
        "--font",
        metavar="PATH",
        help=(
            "font file; relative paths use the current directory "
            f"(default: {DEFAULT_FONT.as_posix()})"
        ),
    )
    parser.add_argument(
        "--fps",
        type=int,
        metavar="FPS",
        help=(f"target presentation rate, {MIN_FPS}..{MAX_FPS} frames/s (default: {DEFAULT_FPS})"),
    )
    parser.add_argument(
        "--margin",
        type=float,
        metavar="RATIO",
        help=(
            "viewport fraction reserved on every edge, 0 <= RATIO < 0.5 "
            f"(default: {DEFAULT_MARGIN})"
        ),
    )
    parser.add_argument(
        "--seed",
        type=int,
        metavar="INTEGER",
        help=f"signed 64-bit deterministic effect seed (default: {DEFAULT_SEED})",
    )
    parser.add_argument(
        "--scene",
        metavar="NAME",
        help=f"built-in ambient scene ({', '.join(scene_names())})",
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        help=(
            "UTF-8 TOML file; relative paths use the current directory "
            "(default: %%APPDATA%%\\mojit\\config.toml when present)"
        ),
    )
    listing = parser.add_mutually_exclusive_group()
    listing.add_argument(
        "--list-effects",
        action="store_true",
        help="print available effect IDs and exit; accepts no rendering options",
    )
    listing.add_argument(
        "--list-scenes",
        action="store_true",
        help="print built-in scene names and exit; accepts no rendering options",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="show Python tracebacks for diagnostic failures",
    )
    return parser


def parse_cli(argv: Sequence[str]) -> ParsedCli:
    """Parse explicit arguments without reading process globals or streams."""
    namespace = _parser().parse_args(list(argv))
    try:
        overrides = ConfigOverrides(
            effect=namespace.effect,
            orientation=namespace.orientation,
            font=namespace.font,
            fps=namespace.fps,
            margin=namespace.margin,
            seed=namespace.seed,
            scene=namespace.scene,
        )
    except ConfigValidationError as error:
        raise CliUsageError(str(error)) from error

    if namespace.list_effects:
        mode = CommandMode.LIST_EFFECTS
    elif namespace.list_scenes:
        mode = CommandMode.LIST_SCENES
    else:
        mode = CommandMode.RUN
    if mode is not CommandMode.RUN:
        if namespace.text is not None:
            raise CliUsageError(f"--{mode.value} does not accept text")
        if namespace.config is not None:
            raise CliUsageError(f"--{mode.value} does not accept --config")
        if overrides != ConfigOverrides():
            raise CliUsageError(f"--{mode.value} does not accept rendering options")
    if namespace.config == "-":
        raise CliUsageError("--config - is not supported; stdin is reserved for text")

    return ParsedCli(
        mode=mode,
        text=namespace.text,
        config_path=namespace.config,
        overrides=overrides,
        debug=namespace.debug,
    )


def prepare_run(
    parsed: ParsedCli,
    *,
    stdin: TextIO,
    environ: Mapping[str, str],
    cwd: Path,
) -> PreparedRun:
    """Assemble a validated request without querying or mutating the terminal."""
    if parsed.mode is not CommandMode.RUN:
        raise CliUsageError("only run mode can produce a prepared request")

    document = load_config_document(parsed.config_path, environ=environ, cwd=cwd)
    file_overrides = ConfigOverrides()
    config_dir = None
    if document is not None:
        file_overrides = parse_toml_config(document.text)
        config_dir = document.source.parent

    config = resolve_config(
        parsed.overrides,
        file_overrides,
        cwd=cwd,
        config_dir=config_dir,
        debug=parsed.debug,
    )
    get_effect(config.effect)
    if config.scene is not None:
        get_scene_builder(config.scene)
    text = resolve_input_text(parsed.text, stdin)
    font = load_font_resource(config.font)
    require_shaping_capability()

    return PreparedRun(
        text=text,
        effect_id=config.effect,
        orientation=config.orientation,
        font_data=font.data,
        font_fingerprint=font.fingerprint,
        fps=config.fps,
        margin=config.margin,
        seed=config.seed,
        debug=config.debug,
        scene_id=config.scene,
        scene_layers=config.scene_layers,
    )


_USER_ERRORS = (
    CliUsageError,
    ConfigFileError,
    ConfigSyntaxError,
    ConfigValidationError,
    InputTextError,
    FontResourceError,
    JapaneseSegmentationError,
    ShapingUnavailableError,
    UnknownEffectError,
    UnknownSceneError,
    WezTermPreflightError,
)


def _configure_piped_stdin(stdin: TextIO) -> None:
    reconfigure = getattr(stdin, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8", errors="strict")


def _create_backend(
    environ: Mapping[str, str],
    stdout: TextIO,
) -> WezTermBackend:
    binary = getattr(stdout, "buffer", None)
    if binary is None:
        raise WezTermPreflightError("stdout does not expose a binary terminal stream")
    return WezTermBackend.from_environment(
        environ,
        output=cast(BinaryIO, binary),
        output_is_terminal=stdout.isatty(),
    )


def create_rasterizer(request: PreparedRun) -> Rasterizer:
    """Bind one invocation's immutable language analysis to the core rasterizer."""
    phrases = (
        segment_japanese_phrases(request.text)
        if request.orientation is Orientation.HORIZONTAL
        else (request.text,)
    )
    return partial(rasterize_text_mask, phrases=phrases)


def execute_prepared_run(
    request: PreparedRun,
    *,
    backend: WezTermBackend,
    clock: SystemMonotonicClock,
    rasterizer: Rasterizer,
) -> None:
    """Run one lifecycle without losing either primary or cleanup failures."""
    backend.preflight()
    primary: BaseException | None = None
    try:
        backend.enter()
        run_animation(request, backend=backend, clock=clock, rasterizer=rasterizer)
    except BaseException as error:  # noqa: BLE001  # cleanup includes interrupt
        primary = error

    try:
        backend.restore()
    except BaseException as cleanup:  # cleanup failure must be retained
        raise LifecycleFailure(primary, cleanup) from cleanup

    if isinstance(primary, KeyboardInterrupt):
        return
    if primary is not None:
        raise primary


def main(argv: Sequence[str] | None = None) -> int:
    """Parse and validate one invocation, mapping failures to stable exit codes."""
    parsed: ParsedCli | None = None
    try:
        parsed = parse_cli(sys.argv[1:] if argv is None else argv)
        if parsed.mode is CommandMode.LIST_EFFECTS:
            print(*effect_names(), sep="\n")
            return 0
        if parsed.mode is CommandMode.LIST_SCENES:
            print(*scene_names(), sep="\n")
            return 0
        if parsed.text is None:
            _configure_piped_stdin(sys.stdin)
        request = prepare_run(parsed, stdin=sys.stdin, environ=os.environ, cwd=Path.cwd().resolve())
        rasterizer = create_rasterizer(request)
        backend = _create_backend(os.environ, sys.stdout)
        execute_prepared_run(
            request,
            backend=backend,
            clock=SystemMonotonicClock(),
            rasterizer=rasterizer,
        )
        return 0
    except _CliExit as exit_request:
        return exit_request.status
    except _USER_ERRORS as error:
        if parsed is not None and parsed.debug:
            traceback.print_exc()
        else:
            print(f"mojit: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 0
    except Exception as error:  # noqa: BLE001  # pragma: no cover - process boundary
        if parsed is not None and parsed.debug:
            traceback.print_exc()
        else:
            print(f"mojit: unexpected failure: {error}", file=sys.stderr)
        return 1
