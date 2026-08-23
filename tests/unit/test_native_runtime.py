from __future__ import annotations

import os
from pathlib import Path

import pytest

from mojit import native_runtime


class _Handle:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def _clear_activation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(native_runtime, "_active_runtime", None)
    monkeypatch.setattr(native_runtime, "_dll_directory_handle", None)
    monkeypatch.setattr(native_runtime, "_fribidi_handle", None)


def _native_tree(root: Path) -> Path:
    directory = root / "_native" / "win_amd64"
    directory.mkdir(parents=True)
    (directory / "libfribidi-0.dll").write_bytes(b"test")
    (root / "_native" / "manifest.toml").write_text("schema_version = 1\n", encoding="utf-8")
    return directory


def test_activation_is_exact_idempotent_and_retains_handle(tmp_path: Path) -> None:
    expected = _native_tree(tmp_path)
    calls: list[str] = []
    handle = _Handle()

    def register(path: str) -> _Handle:
        calls.append(path)
        return handle

    first = native_runtime.activate_native_runtime(
        package_root=tmp_path,
        system="win32",
        machine="AMD64",
        add_dll_directory=register,
        load_library=lambda _: "library-handle",
        set_secure_dll_search=lambda: None,
    )
    second = native_runtime.activate_native_runtime(
        package_root=tmp_path,
        system="ignored",
        machine="ignored",
        add_dll_directory=lambda _: pytest.fail("registered twice"),
    )

    assert first is second
    assert first.directory == expected
    assert calls == [str(expected)]
    assert native_runtime._dll_directory_handle is handle
    assert native_runtime._fribidi_handle == "library-handle"
    assert not handle.closed


@pytest.mark.parametrize(
    ("system", "machine", "message"),
    [
        ("linux", "x86_64", "requires Windows x64"),
        ("win32", "ARM64", "requires Windows x64"),
    ],
)
def test_activation_rejects_unsupported_targets(
    tmp_path: Path, system: str, machine: str, message: str
) -> None:
    with pytest.raises(native_runtime.NativeRuntimeError, match=message):
        native_runtime.activate_native_runtime(
            package_root=tmp_path,
            system=system,
            machine=machine,
            add_dll_directory=lambda _: _Handle(),
            load_library=lambda _: object(),
            set_secure_dll_search=lambda: None,
        )


@pytest.mark.parametrize("missing", ["dll", "manifest"])
def test_activation_fails_closed_for_incomplete_install(tmp_path: Path, missing: str) -> None:
    directory = _native_tree(tmp_path)
    target = (
        directory / "libfribidi-0.dll"
        if missing == "dll"
        else tmp_path / "_native" / "manifest.toml"
    )
    target.unlink()

    with pytest.raises(native_runtime.NativeRuntimeError, match="installation is incomplete"):
        native_runtime.activate_native_runtime(
            package_root=tmp_path,
            system="win32",
            machine="x86_64",
            add_dll_directory=lambda _: pytest.fail("must fail before registration"),
            load_library=lambda _: pytest.fail("must fail before load"),
            set_secure_dll_search=lambda: pytest.fail("must fail before configuration"),
        )


def test_activation_maps_registration_failure_without_changing_path(tmp_path: Path) -> None:
    _native_tree(tmp_path)
    original_path = os.environ.get("PATH")

    def fail(_: str) -> _Handle:
        raise OSError("loader refused directory")

    with pytest.raises(native_runtime.NativeRuntimeError, match="loader refused directory"):
        native_runtime.activate_native_runtime(
            package_root=tmp_path,
            system="win32",
            machine="AMD64",
            add_dll_directory=fail,
            load_library=lambda _: object(),
            set_secure_dll_search=lambda: None,
        )

    assert os.environ.get("PATH") == original_path
    assert native_runtime._active_runtime is None
    assert native_runtime._dll_directory_handle is None


def test_activation_closes_directory_handle_when_absolute_load_fails(tmp_path: Path) -> None:
    _native_tree(tmp_path)
    handle = _Handle()

    def load(_: str) -> object:
        raise OSError("invalid PE image")

    with pytest.raises(native_runtime.NativeRuntimeError, match="invalid PE image"):
        native_runtime.activate_native_runtime(
            package_root=tmp_path,
            system="win32",
            machine="AMD64",
            add_dll_directory=lambda _: handle,
            load_library=load,
            set_secure_dll_search=lambda: None,
        )

    assert handle.closed
    assert native_runtime._active_runtime is None
    assert native_runtime._fribidi_handle is None


def test_activation_maps_secure_search_failure_before_registration(tmp_path: Path) -> None:
    _native_tree(tmp_path)

    def fail() -> None:
        raise OSError("SetDefaultDllDirectories failed")

    with pytest.raises(native_runtime.NativeRuntimeError, match="secure Windows DLL search"):
        native_runtime.activate_native_runtime(
            package_root=tmp_path,
            system="win32",
            machine="AMD64",
            add_dll_directory=lambda _: pytest.fail("must fail before registration"),
            load_library=lambda _: pytest.fail("must fail before load"),
            set_secure_dll_search=fail,
        )
