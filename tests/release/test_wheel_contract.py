from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from tools.release.artifact_contract import (
    BUNDLE_MEMBERS,
    create_deterministic_zip,
    inspect_bundle,
    inspect_wheel,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_runtime_version_matches_release_metadata() -> None:
    import mojit

    assert mojit.__version__ == "1.0.0"


def test_built_wheel_is_closed_windows_x64_artifact(tmp_path: Path) -> None:
    subprocess.run(
        (
            sys.executable,
            "-m",
            "build",
            "--wheel",
            "--no-isolation",
            "--outdir",
            str(tmp_path),
        ),
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    wheel = next(tmp_path.glob("*.whl"))

    evidence = inspect_wheel(wheel)

    assert evidence["wheel"] == "mojit-1.0.0-py3-none-win_amd64.whl"
    with zipfile.ZipFile(wheel) as archive:
        assert not any(
            name.startswith(("tests/", "spikes/", "vendor/")) for name in archive.namelist()
        )


def test_offline_bundle_contains_verified_installer_and_exact_inventory(tmp_path: Path) -> None:
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    payload_names = BUNDLE_MEMBERS - {"WHEELHOUSE_SHA256SUMS.txt"}
    lines = []
    for name in sorted(payload_names):
        data = f"fixture:{name}".encode()
        (wheelhouse / name).write_bytes(data)
        lines.append(f"{hashlib.sha256(data).hexdigest()}  {name}")
    (wheelhouse / "WHEELHOUSE_SHA256SUMS.txt").write_text(
        "\n".join(lines) + "\n",
        encoding="ascii",
    )
    bundle = tmp_path / "mojit-1.0.0-windows-x64-wheelhouse.zip"

    create_deterministic_zip(wheelhouse, bundle)

    assert inspect_bundle(bundle) == {"bundle": bundle.name, "members": len(BUNDLE_MEMBERS)}


def test_uninstaller_refuses_unowned_directory(tmp_path: Path) -> None:
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    assert powershell is not None
    unowned = tmp_path / "unowned"
    unowned.mkdir()
    sentinel = unowned / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")

    result = subprocess.run(
        (
            powershell,
            "-NoProfile",
            "-File",
            str(PROJECT_ROOT / "tools" / "release" / "install.ps1"),
            "-Uninstall",
            "-InstallRoot",
            str(unowned),
            "-PathScope",
            "None",
        ),
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "unowned installation directory" in result.stderr
    assert sentinel.read_text(encoding="utf-8") == "keep"
