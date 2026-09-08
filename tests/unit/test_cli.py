from __future__ import annotations

import io
import re

import pytest

from mojit import cli as cli_module
from mojit.application.input_text import InputTextError
from mojit.cli import CliUsageError, CommandMode, main, parse_cli
from mojit.core.models import Orientation


def test_parser_accepts_every_rendering_flag() -> None:
    parsed = parse_cli(
        [
            "警告",
            "-e",
            "glitch",
            "--vertical",
            "--font",
            "font.ttf",
            "--fps",
            "15",
            "--margin",
            "0.1",
            "--seed",
            "42",
            "--config",
            "settings.toml",
            "--scene",
            "rainy-night",
            "--debug",
        ]
    )

    assert parsed.mode is CommandMode.RUN
    assert parsed.text == "警告"
    assert parsed.config_path == "settings.toml"
    assert parsed.debug is True
    assert parsed.overrides.orientation is Orientation.VERTICAL
    assert parsed.overrides.effect == "glitch"
    assert parsed.overrides.font == "font.ttf"
    assert parsed.overrides.fps == 15
    assert parsed.overrides.margin == 0.1
    assert parsed.overrides.seed == 42
    assert parsed.overrides.scene == "rainy-night"


def test_horizontal_is_an_explicit_override() -> None:
    assert parse_cli(["--horizontal"]).overrides.orientation is Orientation.HORIZONTAL


def test_text_is_optional_for_stdin_resolution() -> None:
    assert parse_cli([]).text is None


@pytest.mark.parametrize(
    "argv",
    [
        ["--vertical", "--horizontal"],
        ["--fps", "0"],
        ["--fps", "16"],
        ["--margin", "0.5"],
        ["--seed", str(2**63)],
        ["--effect", "Neon"],
        ["--scene", "Rainy Night"],
        ["--config", "-"],
        ["--unknown"],
    ],
)
def test_invalid_cli_is_mapped_to_usage_error(argv: list[str]) -> None:
    with pytest.raises(CliUsageError):
        parse_cli(argv)


@pytest.mark.parametrize(
    "extra",
    [
        ["text"],
        ["--config", "x.toml"],
        ["--effect", "neon"],
        ["--vertical"],
        ["--font", "font.ttf"],
        ["--fps", "8"],
        ["--margin", "0.1"],
        ["--seed", "0"],
        ["--scene", "space"],
    ],
)
def test_list_mode_rejects_render_inputs(extra: list[str]) -> None:
    with pytest.raises(CliUsageError):
        parse_cli(["--list-effects", *extra])


def test_list_mode_allows_debug_only() -> None:
    parsed = parse_cli(["--list-effects", "--debug"])
    assert parsed.mode is CommandMode.LIST_EFFECTS
    assert parsed.debug is True


@pytest.mark.parametrize("help_option", ["-h", "--help"])
def test_help_documents_complete_cli_contract(
    help_option: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main([help_option]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert re.search(r"(?m)^\s+-e(?: ID)?, --effect ID\s", captured.out)
    normalized_help = " ".join(captured.out.split())
    for expected in (
        "usage: mojit",
        "Display large animated Unicode text in WezTerm.",
        "TEXT",
        "-h, --help",
        "--vertical",
        "--horizontal",
        "--font PATH",
        "--fps FPS",
        "--margin RATIO",
        "--seed INTEGER",
        "--config PATH",
        "--list-effects",
        "--scene NAME",
        "--list-scenes",
        "--debug",
        "built-in default: neon",
        "target presentation rate, 1..15 frames/s (built-in default: 8)",
        "0 <= RATIO < 0.5",
        "Configuration precedence:",
        "command line > --config PATH > %APPDATA%\\mojit\\config.toml",
        "Examples:",
        "Exit status:",
    ):
        assert expected in normalized_help


def test_usage_error_has_no_traceback(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--fps", "0"]) == 2
    captured = capsys.readouterr()
    assert "fps" in captured.err
    assert "Traceback" not in captured.err
    assert "\x1b" not in captured.out + captured.err


def test_list_mode_does_not_touch_stdin(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class PoisonStdin(io.StringIO):
        def reconfigure(self, **kwargs: object) -> None:
            raise AssertionError("stdin was reconfigured")

        def isatty(self) -> bool:
            raise AssertionError("stdin was inspected")

    monkeypatch.setattr("sys.stdin", PoisonStdin())
    assert main(["--list-effects"]) == 0
    captured = capsys.readouterr()
    assert captured.out == "chromatic\nglitch\nneon\npulse\n"
    assert captured.err == ""


def test_scene_list_mode_is_sorted_and_does_not_touch_stdin(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class PoisonStdin(io.StringIO):
        def reconfigure(self, **kwargs: object) -> None:
            raise AssertionError("stdin was reconfigured")

    monkeypatch.setattr("sys.stdin", PoisonStdin())
    assert main(["--list-scenes"]) == 0
    captured = capsys.readouterr()
    assert captured.out == "rainy-night\nsnowfall\nspace\n"
    assert captured.err == ""


def test_debug_exposes_traceback_at_outer_boundary(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise InputTextError("bad text")

    monkeypatch.setattr(cli_module, "prepare_run", fail)

    assert main(["猫", "--debug"]) == 2
    assert "Traceback" in capsys.readouterr().err


def test_unexpected_failure_uses_exit_one_without_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(cli_module, "prepare_run", fail)

    assert main(["猫"]) == 1
    captured = capsys.readouterr()
    assert "unexpected failure: boom" in captured.err
    assert "Traceback" not in captured.err
