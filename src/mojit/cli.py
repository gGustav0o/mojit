"""Command-line parsing and pre-terminal composition root."""

from __future__ import annotations

import argparse
import os
import sys
import traceback
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import BinaryIO, TextIO, cast

from mojit.adapters.clock import SystemMonotonicClock
from mojit.adapters.config_file import ConfigFileError, load_config_document
from mojit.adapters.font_resource import FontResourceError, load_font_resource
from mojit.adapters.wezterm.backend import WezTermBackend
from mojit.adapters.wezterm.errors import WezTermPreflightError
from mojit.application.input_text import InputTextError, resolve_input_text
from mojit.application.request import PreparedRun
from mojit.application.runtime import run_animation
from mojit.config.models import ConfigOverrides, ConfigValidationError
from mojit.config.resolve import resolve_config
from mojit.config.toml import ConfigSyntaxError, parse_toml_config
from mojit.core.models import Orientation
from mojit.core.typography import ShapingUnavailableError, require_shaping_capability
from mojit.effects.registry import UnknownEffectError, effect_names, get_effect


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


@dataclass(frozen=True, slots=True)
class ParsedCli:
    mode: CommandMode
    text: str | None
    config_path: str | None
    overrides: ConfigOverrides
    debug: bool


def _parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(prog="mojit", description="Render animated Unicode in WezTerm")
    parser.add_argument("text", nargs="?", help="one line of Unicode text")
    parser.add_argument("--effect", "-e")
    orientation = parser.add_mutually_exclusive_group()
    orientation.add_argument(
        "--vertical", dest="orientation", action="store_const", const=Orientation.VERTICAL
    )
    orientation.add_argument(
        "--horizontal",
        dest="orientation",
        action="store_const",
        const=Orientation.HORIZONTAL,
    )
    parser.add_argument("--font")
    parser.add_argument("--fps", type=int)
    parser.add_argument("--margin", type=float)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--config")
    parser.add_argument("--list-effects", action="store_true")
    parser.add_argument("--debug", action="store_true")
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
        )
    except ConfigValidationError as error:
        raise CliUsageError(str(error)) from error

    mode = CommandMode.LIST_EFFECTS if namespace.list_effects else CommandMode.RUN
    if mode is CommandMode.LIST_EFFECTS:
        if namespace.text is not None:
            raise CliUsageError("--list-effects does not accept text")
        if namespace.config is not None:
            raise CliUsageError("--list-effects does not accept --config")
        if overrides != ConfigOverrides():
            raise CliUsageError("--list-effects does not accept rendering options")
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
    )


_USER_ERRORS = (
    CliUsageError,
    ConfigFileError,
    ConfigSyntaxError,
    ConfigValidationError,
    InputTextError,
    FontResourceError,
    ShapingUnavailableError,
    UnknownEffectError,
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


def execute_prepared_run(
    request: PreparedRun,
    *,
    backend: WezTermBackend,
    clock: SystemMonotonicClock,
) -> None:
    """Run one lifecycle without losing either primary or cleanup failures."""
    backend.preflight()
    primary: BaseException | None = None
    try:
        backend.enter()
        run_animation(request, backend=backend, clock=clock)
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
        if parsed.text is None:
            _configure_piped_stdin(sys.stdin)
        request = prepare_run(parsed, stdin=sys.stdin, environ=os.environ, cwd=Path.cwd().resolve())
        backend = _create_backend(os.environ, sys.stdout)
        execute_prepared_run(
            request,
            backend=backend,
            clock=SystemMonotonicClock(),
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
