"""Early, package-relative activation of mojit's native text dependency."""

from __future__ import annotations

import ctypes
import os
import platform
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Protocol

_NATIVE_DIRECTORY = Path("_native") / "win_amd64"
_MANIFEST = Path("_native") / "manifest.toml"
_FRIBIDI_DLL = "libfribidi-0.dll"
_SUPPORTED_MACHINES = frozenset({"AMD64", "x86_64"})
_SECURE_DLL_SEARCH_FLAGS = 0x1000 | 0x0400  # DEFAULT_DIRS | USER_DIRS


class _DllDirectoryHandle(Protocol):
    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class NativeRuntime:
    directory: Path
    fribidi_dll: Path
    manifest: Path


class NativeRuntimeError(RuntimeError):
    """The packaged Windows native runtime cannot be activated."""


_activation_lock = Lock()
_active_runtime: NativeRuntime | None = None
_dll_directory_handle: _DllDirectoryHandle | None = None
_fribidi_handle: object | None = None


def _package_root() -> Path:
    return Path(__file__).resolve().parent


def _set_secure_dll_search() -> None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    configure = kernel32.SetDefaultDllDirectories
    configure.argtypes = (ctypes.c_ulong,)
    configure.restype = ctypes.c_int
    if not configure(_SECURE_DLL_SEARCH_FLAGS):
        raise ctypes.WinError(ctypes.get_last_error())


def activate_native_runtime(
    *,
    package_root: Path | None = None,
    system: str | None = None,
    machine: str | None = None,
    add_dll_directory: Callable[[str], _DllDirectoryHandle] | None = None,
    load_library: Callable[[str], object] | None = None,
    set_secure_dll_search: Callable[[], None] | None = None,
) -> NativeRuntime:
    """Register the exact packaged DLL directory once and retain its handle."""
    global _active_runtime, _dll_directory_handle, _fribidi_handle

    with _activation_lock:
        if _active_runtime is not None:
            return _active_runtime

        actual_system = sys.platform if system is None else system
        if actual_system != "win32":
            raise NativeRuntimeError(
                f"unsupported platform {actual_system!r}; mojit v1 requires Windows x64"
            )

        actual_machine = platform.machine() if machine is None else machine
        if actual_machine not in _SUPPORTED_MACHINES:
            raise NativeRuntimeError(
                f"unsupported architecture {actual_machine!r}; mojit v1 requires Windows x64"
            )

        root = _package_root() if package_root is None else package_root.resolve()
        directory = root / _NATIVE_DIRECTORY
        dll = directory / _FRIBIDI_DLL
        manifest = root / _MANIFEST
        missing = [str(path) for path in (directory, dll, manifest) if not path.exists()]
        if missing:
            raise NativeRuntimeError(
                "installation is incomplete; missing packaged native resource(s): "
                + ", ".join(missing)
                + "; reinstall mojit from the verified wheelhouse"
            )

        secure_search = (
            _set_secure_dll_search if set_secure_dll_search is None else set_secure_dll_search
        )
        try:
            secure_search()
        except OSError as error:
            raise NativeRuntimeError(f"cannot enable secure Windows DLL search: {error}") from error

        register = add_dll_directory
        if register is None:
            register = getattr(os, "add_dll_directory", None)
        if register is None:
            raise NativeRuntimeError("this Python runtime cannot register a Windows DLL directory")

        try:
            handle = register(str(directory))
        except OSError as error:
            raise NativeRuntimeError(
                f"cannot activate packaged native runtime at {directory}: {error}"
            ) from error

        load = ctypes.WinDLL if load_library is None else load_library
        try:
            library = load(str(dll))
        except OSError as error:
            handle.close()
            raise NativeRuntimeError(
                f"cannot load packaged FriBiDi runtime at {dll}: {error}"
            ) from error

        runtime = NativeRuntime(directory=directory, fribidi_dll=dll, manifest=manifest)
        _dll_directory_handle = handle
        _fribidi_handle = library
        _active_runtime = runtime
        return runtime
