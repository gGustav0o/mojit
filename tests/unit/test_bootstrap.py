from __future__ import annotations

import sys
from types import ModuleType

import pytest

from mojit import bootstrap
from mojit.native_runtime import NativeRuntimeError


def test_bootstrap_activates_native_runtime_before_importing_cli(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    fake_cli = ModuleType("mojit.cli")

    def activate() -> None:
        events.append("activate")
        assert "mojit.cli" not in sys.modules
        monkeypatch.setitem(sys.modules, "mojit.cli", fake_cli)

    def cli_main(argv: object) -> int:
        events.append(f"cli:{argv!r}")
        return 17

    fake_cli.main = cli_main  # type: ignore[attr-defined]
    monkeypatch.delitem(sys.modules, "mojit.cli", raising=False)
    monkeypatch.setattr(bootstrap, "activate_native_runtime", activate)

    assert bootstrap.main(["--list-effects"]) == 17
    assert events == ["activate", "cli:['--list-effects']"]


def test_bootstrap_maps_native_failure_before_cli_import(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delitem(sys.modules, "mojit.cli", raising=False)

    def fail() -> None:
        raise NativeRuntimeError("packaged DLL missing")

    monkeypatch.setattr(bootstrap, "activate_native_runtime", fail)

    assert bootstrap.main([]) == 2
    assert "packaged DLL missing" in capsys.readouterr().err
    assert "mojit.cli" not in sys.modules
