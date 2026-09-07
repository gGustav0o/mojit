"""Windows process-memory sampling shared by manual and live longevity probes."""

from __future__ import annotations

import ctypes
import os
import sys
from dataclasses import asdict, dataclass


class _ProcessMemoryCountersEx(ctypes.Structure):
    _fields_ = (
        ("cb", ctypes.c_ulong),
        ("page_fault_count", ctypes.c_ulong),
        ("peak_working_set_size", ctypes.c_size_t),
        ("working_set_size", ctypes.c_size_t),
        ("quota_peak_paged_pool_usage", ctypes.c_size_t),
        ("quota_paged_pool_usage", ctypes.c_size_t),
        ("quota_peak_non_paged_pool_usage", ctypes.c_size_t),
        ("quota_non_paged_pool_usage", ctypes.c_size_t),
        ("pagefile_usage", ctypes.c_size_t),
        ("peak_pagefile_usage", ctypes.c_size_t),
        ("private_usage", ctypes.c_size_t),
    )


@dataclass(frozen=True, slots=True)
class ProcessMemory:
    """One process-level sample from the Windows memory manager."""

    pid: int
    working_set_bytes: int
    private_bytes: int

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


def current_process_memory() -> ProcessMemory:
    """Measure working-set and private bytes for the calling Python process."""
    if sys.platform != "win32":
        raise RuntimeError("process memory sampling is supported only on Windows")

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    psapi.GetProcessMemoryInfo.argtypes = (
        ctypes.c_void_p,
        ctypes.POINTER(_ProcessMemoryCountersEx),
        ctypes.c_ulong,
    )
    psapi.GetProcessMemoryInfo.restype = ctypes.c_int
    counters = _ProcessMemoryCountersEx()
    counters.cb = ctypes.sizeof(counters)
    if not psapi.GetProcessMemoryInfo(
        kernel32.GetCurrentProcess(),
        ctypes.byref(counters),
        counters.cb,
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    return ProcessMemory(
        pid=os.getpid(),
        working_set_bytes=int(counters.working_set_size),
        private_bytes=int(counters.private_usage),
    )
