from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pytest

from mojit import cli
from mojit.adapters.config_file import ConfigFileError
from mojit.adapters.font_resource import FontResource, FontResourceError
from mojit.application.input_text import InputTextError
from mojit.core.models import Orientation
from mojit.core.typography import ShapingUnavailableError


class Pipe(io.StringIO):
    def isatty(self) -> bool:
        return False


class PoisonPipe(io.StringIO):
    def isatty(self) -> bool:
        raise AssertionError("stdin was inspected")

    def read(self, *args: object, **kwargs: object) -> str:
        raise AssertionError("stdin was read")


@pytest.fixture
def fake_preflight(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    loaded: list[Path] = []
    data = b"valid-font-resource"

    def load(path: str | Path) -> FontResource:
        resolved = Path(path)
        loaded.append(resolved)
        return FontResource(
            source=resolved,
            data=data,
            fingerprint=hashlib.sha256(data).hexdigest(),
        )

    monkeypatch.setattr(cli, "load_font_resource", load)
    monkeypatch.setattr(cli, "require_shaping_capability", lambda: None)
    return loaded


def test_positional_text_with_defaults(tmp_path: Path, fake_preflight: list[Path]) -> None:
    request = cli.prepare_run(
        cli.parse_cli(["電脳世界"]), stdin=PoisonPipe(), environ={}, cwd=tmp_path
    )

    assert request.text == "電脳世界"
    assert request.effect_id == "neon"
    assert request.orientation is Orientation.HORIZONTAL
    assert request.fps == 30
    assert request.margin == 0.08
    assert request.seed == 0
    assert len(fake_preflight) == 1


def test_piped_japanese_text(tmp_path: Path, fake_preflight: list[Path]) -> None:
    request = cli.prepare_run(
        cli.parse_cli([]), stdin=Pipe("少女終末旅行\r\n"), environ={}, cwd=tmp_path
    )
    assert request.text == "少女終末旅行"


def test_explicit_config_and_all_cli_overrides(tmp_path: Path, fake_preflight: list[Path]) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_path = config_dir / "mojit.toml"
    config_path.write_text(
        'effect = "pulse"\norientation = "vertical"\nfont = "file.ttf"\n'
        "fps = 20\nmargin = 0.2\nseed = 9\n",
        encoding="utf-8",
    )

    request = cli.prepare_run(
        cli.parse_cli(
            [
                "猫",
                "--config",
                str(config_path),
                "--effect",
                "glitch",
                "--horizontal",
                "--font",
                "cli.ttf",
                "--fps",
                "60",
                "--margin",
                "0",
                "--seed",
                "0",
                "--debug",
            ]
        ),
        stdin=PoisonPipe(),
        environ={},
        cwd=tmp_path,
    )

    assert request.effect_id == "glitch"
    assert request.orientation is Orientation.HORIZONTAL
    assert fake_preflight[-1] == tmp_path / "cli.ttf"
    assert (request.fps, request.margin, request.seed, request.debug) == (60, 0.0, 0, True)


def test_config_relative_font_uses_config_directory(
    tmp_path: Path, fake_preflight: list[Path]
) -> None:
    appdata = tmp_path / "appdata"
    path = appdata / "mojit" / "config.toml"
    path.parent.mkdir(parents=True)
    path.write_text('font = "fonts/cjk.ttf"\n', encoding="utf-8")

    cli.prepare_run(
        cli.parse_cli(["猫"]),
        stdin=PoisonPipe(),
        environ={"APPDATA": str(appdata)},
        cwd=tmp_path,
    )

    assert fake_preflight[-1] == path.parent / "fonts" / "cjk.ttf"


def test_invalid_input_fails_before_font_loading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        cli,
        "load_font_resource",
        lambda path: pytest.fail(f"font was loaded for invalid input: {path}"),
    )
    with pytest.raises(InputTextError):
        cli.prepare_run(cli.parse_cli([]), stdin=Pipe("\n"), environ={}, cwd=tmp_path)


def test_malformed_explicit_config_fails_before_font_loading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "broken.toml"
    path.write_text("fps = [", encoding="utf-8")
    monkeypatch.setattr(
        cli,
        "load_font_resource",
        lambda font_path: pytest.fail(f"font was loaded: {font_path}"),
    )
    with pytest.raises(cli.ConfigSyntaxError):
        cli.prepare_run(
            cli.parse_cli(["猫", "--config", str(path)]),
            stdin=PoisonPipe(),
            environ={},
            cwd=tmp_path,
        )


def test_explicit_missing_config_is_mapped_before_preflight(tmp_path: Path) -> None:
    with pytest.raises(ConfigFileError, match="missing.toml"):
        cli.prepare_run(
            cli.parse_cli(["猫", "--config", "missing.toml"]),
            stdin=PoisonPipe(),
            environ={},
            cwd=tmp_path,
        )


def test_invalid_utf8_stdin_is_mapped_before_font_loading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class InvalidUtf8Pipe(Pipe):
        def read(self, size: int = -1) -> str:
            raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid")

    monkeypatch.setattr(
        cli,
        "load_font_resource",
        lambda path: pytest.fail(f"font was loaded: {path}"),
    )
    with pytest.raises(InputTextError, match="UTF-8"):
        cli.prepare_run(cli.parse_cli([]), stdin=InvalidUtf8Pipe(), environ={}, cwd=tmp_path)


def test_font_failure_precedes_shaping(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_font(path: str | Path) -> FontResource:
        raise FontResourceError(f"bad font: {path}")

    monkeypatch.setattr(cli, "load_font_resource", fail_font)
    monkeypatch.setattr(cli, "require_shaping_capability", lambda: pytest.fail("shaping"))

    with pytest.raises(FontResourceError, match="bad font"):
        cli.prepare_run(cli.parse_cli(["猫"]), stdin=PoisonPipe(), environ={}, cwd=tmp_path)


def test_shaping_failure_is_exposed_after_font_validation(
    tmp_path: Path, fake_preflight: list[Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_shaping() -> None:
        raise ShapingUnavailableError("Raqm/FriBiDi unavailable")

    monkeypatch.setattr(cli, "require_shaping_capability", fail_shaping)

    with pytest.raises(ShapingUnavailableError, match="Raqm/FriBiDi"):
        cli.prepare_run(cli.parse_cli(["猫"]), stdin=PoisonPipe(), environ={}, cwd=tmp_path)
    assert len(fake_preflight) == 1


def test_list_mode_main_performs_no_config_font_or_shaping_io(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "load_config_document", lambda *args, **kwargs: pytest.fail("config"))
    monkeypatch.setattr(cli, "load_font_resource", lambda *args, **kwargs: pytest.fail("font"))
    monkeypatch.setattr(cli, "require_shaping_capability", lambda: pytest.fail("shaping"))

    assert cli.main(["--list-effects"]) == 1
    captured = capsys.readouterr()
    assert "\x1b" not in captured.out + captured.err
