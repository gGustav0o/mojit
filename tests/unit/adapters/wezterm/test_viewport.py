from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace

import pytest

from mojit.adapters.wezterm import viewport as viewport_module
from mojit.adapters.wezterm.errors import ViewportQueryError, WezTermPreflightError
from mojit.adapters.wezterm.viewport import (
    MAX_STDOUT_BYTES,
    VIEWPORT_TIMEOUT_SECONDS,
    WEZTERM_LIST_COMMAND,
    CommandResult,
    PaneGeometry,
    parse_pane_geometry,
    parse_pane_id,
    query_pane_geometry,
    run_wezterm_cli,
)
from mojit.core.models import Viewport


def _pane(
    pane_id: object = 2,
    *,
    rows: object = 24,
    cols: object = 80,
    width: object = 800,
    height: object = 600,
    dpi: object = 96,
) -> dict[str, object]:
    return {
        "pane_id": pane_id,
        "size": {
            "rows": rows,
            "cols": cols,
            "pixel_width": width,
            "pixel_height": height,
            "dpi": dpi,
        },
    }


def _document(*panes: object) -> str:
    return json.dumps(list(panes))


def test_parse_pane_id_is_strict_and_explicit() -> None:
    assert parse_pane_id({"WEZTERM_PANE": "0"}) == 0
    assert parse_pane_id({"WEZTERM_PANE": "2048"}) == 2048


@pytest.mark.parametrize(
    "environ",
    [
        {},
        {"WEZTERM_PANE": ""},
        {"WEZTERM_PANE": " 2"},
        {"WEZTERM_PANE": "-1"},
        {"WEZTERM_PANE": "２"},
    ],
)
def test_parse_pane_id_rejects_missing_or_non_ascii_decimal(environ: dict[str, str]) -> None:
    with pytest.raises(WezTermPreflightError, match="WEZTERM_PANE"):
        parse_pane_id(environ)


def test_parse_geometry_selects_exact_pane_and_normalizes_values() -> None:
    geometry = parse_pane_geometry(_document(_pane(1), _pane(2, dpi=96.5)), 2)
    assert geometry == PaneGeometry(2, Viewport(800, 600), columns=80, rows=24, dpi=96.5)


def test_parse_geometry_allows_missing_diagnostic_dpi() -> None:
    pane = _pane()
    assert isinstance(pane["size"], dict)
    pane["size"].pop("dpi")
    assert parse_pane_geometry(_document(pane), 2).dpi is None


def test_parse_geometry_normalizes_wezterm_unknown_dpi_sentinel() -> None:
    assert parse_pane_geometry(_document(_pane(dpi=0)), 2).dpi is None


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ("not json", "invalid JSON"),
        ("{}", "root must be a list"),
        (_document(_pane(1)), "was not returned"),
        (_document(_pane(2), _pane(2)), "more than once"),
        (_document({"pane_id": 2}), "size must be an object"),
        (_document(_pane(rows=0)), "rows"),
        (_document(_pane(cols=True)), "cols"),
        (_document(_pane(width="800")), "pixel_width"),
        (_document(_pane(height=-1)), "pixel_height"),
        (_document(_pane(dpi=-1)), "dpi"),
        (_document(_pane(dpi=float("inf"))), "dpi"),
    ],
)
def test_parse_geometry_rejects_invalid_documents(document: str, message: str) -> None:
    with pytest.raises(ViewportQueryError, match=message):
        parse_pane_geometry(document, 2)


@pytest.mark.parametrize("pane_id", [True, -1, 1.5])
def test_parse_geometry_rejects_invalid_target_id(pane_id: object) -> None:
    with pytest.raises(ViewportQueryError, match="pane_id"):
        parse_pane_geometry(_document(_pane()), pane_id)  # type: ignore[arg-type]


def test_parse_geometry_rejects_non_string_document() -> None:
    with pytest.raises(TypeError, match="document"):
        parse_pane_geometry(object(), 2)  # type: ignore[arg-type]


def test_query_uses_exact_command_timeout_and_strict_utf8() -> None:
    calls: list[tuple[tuple[str, ...], float]] = []

    def runner(command: tuple[str, ...], timeout: float) -> CommandResult:
        calls.append((command, timeout))
        return CommandResult(0, _document(_pane()).encode(), b"")

    geometry = query_pane_geometry(2, runner=runner)
    assert geometry.viewport == Viewport(800, 600)
    assert calls == [(WEZTERM_LIST_COMMAND, VIEWPORT_TIMEOUT_SECONDS)]


@pytest.mark.parametrize(
    ("result", "message"),
    [
        (CommandResult(3, b"", b"socket failed"), "exit code 3: socket failed"),
        (CommandResult(0, b"\xff", b""), "valid UTF-8"),
        (CommandResult(0, b"x" * (MAX_STDOUT_BYTES + 1), b""), "exceeds 1 MiB"),
        (CommandResult(True, b"[]", b""), "return code"),
        (CommandResult(0, "[]", b""), "output must be bytes"),
    ],
)
def test_query_rejects_invalid_process_results(result: CommandResult, message: str) -> None:
    with pytest.raises(ViewportQueryError, match=message):
        query_pane_geometry(2, runner=lambda command, timeout: result)


def test_query_rejects_invalid_runner_result() -> None:
    with pytest.raises(TypeError, match="CommandResult"):
        query_pane_geometry(2, runner=lambda command, timeout: object())  # type: ignore[arg-type]


def test_nonzero_stderr_is_bounded_and_decoded_safely() -> None:
    stderr = b"failure:" + b"x" * 10_000 + b"\xff"
    with pytest.raises(ViewportQueryError) as captured:
        query_pane_geometry(2, runner=lambda command, timeout: CommandResult(1, b"", stderr))
    assert len(str(captured.value)) < 4200


def test_production_runner_uses_no_stdin_no_shell_and_binary_capture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}

    def fake_run(command: tuple[str, ...], **kwargs: object) -> SimpleNamespace:
        observed["command"] = command
        observed.update(kwargs)
        return SimpleNamespace(returncode=0, stdout=b"[]", stderr=b"")

    monkeypatch.setattr(viewport_module.subprocess, "run", fake_run)
    result = run_wezterm_cli(WEZTERM_LIST_COMMAND, 2.0)
    assert result == CommandResult(0, b"[]", b"")
    assert observed["command"] == WEZTERM_LIST_COMMAND
    assert observed["stdin"] is subprocess.DEVNULL
    assert observed["capture_output"] is True
    assert observed["check"] is False
    assert observed["timeout"] == 2.0


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        (subprocess.TimeoutExpired(WEZTERM_LIST_COMMAND, 2), "timed out"),
        (FileNotFoundError(), "not found"),
        (OSError("denied"), "could not start"),
    ],
)
def test_production_runner_maps_start_and_timeout_failures(
    monkeypatch: pytest.MonkeyPatch,
    failure: BaseException,
    message: str,
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise failure

    monkeypatch.setattr(viewport_module.subprocess, "run", fail)
    with pytest.raises(ViewportQueryError, match=message):
        run_wezterm_cli(WEZTERM_LIST_COMMAND, 2.0)
