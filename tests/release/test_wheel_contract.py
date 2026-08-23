from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

from tools.release.artifact_contract import inspect_wheel

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
