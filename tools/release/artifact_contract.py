"""Closed-world inspection and deterministic assembly of Phase 6 artifacts."""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import re
import struct
import zipfile
from pathlib import Path, PurePosixPath

WHEEL_NAME = re.compile(r"^mojit-1\.0\.0-py3-none-win_amd64\.whl$")
BUNDLE_NAME = re.compile(r"^mojit-1\.0\.0-windows-x64-wheelhouse\.zip$")
DIST_INFO = "mojit-1.0.0.dist-info"
EXPECTED_DLL_SHA256 = "4283ba30461395fdf46399b2665176e6f41d11bc7bf6977188120152fde31fd2"
REQUIRED_SUFFIXES = {
    "mojit/bootstrap.py",
    "mojit/native_runtime.py",
    "mojit/_native/manifest.toml",
    "mojit/_native/win_amd64/libfribidi-0.dll",
    f"{DIST_INFO}/METADATA",
    f"{DIST_INFO}/WHEEL",
    f"{DIST_INFO}/entry_points.txt",
    f"{DIST_INFO}/RECORD",
    f"{DIST_INFO}/licenses/LICENSE",
    f"{DIST_INFO}/licenses/THIRD_PARTY_NOTICES.md",
}
BUNDLE_MEMBERS = {
    "WHEELHOUSE_SHA256SUMS.txt",
    "budoux-0.9.0-py3-none-any.whl",
    "install.ps1",
    "mojit-1.0.0-py3-none-win_amd64.whl",
    "numpy-2.4.6-cp311-cp311-win_amd64.whl",
    "numpy-2.4.6-cp312-cp312-win_amd64.whl",
    "numpy-2.4.6-cp313-cp313-win_amd64.whl",
    "numpy-2.4.6-cp314-cp314-win_amd64.whl",
    "pillow-12.3.0-cp311-cp311-win_amd64.whl",
    "pillow-12.3.0-cp312-cp312-win_amd64.whl",
    "pillow-12.3.0-cp313-cp313-win_amd64.whl",
    "pillow-12.3.0-cp314-cp314-win_amd64.whl",
}


class ArtifactContractError(RuntimeError):
    pass


def _member_for_suffix(names: set[str], suffix: str) -> str:
    matches = [name for name in names if name == suffix or name.endswith("/" + suffix)]
    if len(matches) != 1:
        raise ArtifactContractError(f"expected one wheel member ending in {suffix!r}: {matches}")
    return matches[0]


def inspect_wheel(path: Path) -> dict[str, object]:
    if not WHEEL_NAME.fullmatch(path.name):
        raise ArtifactContractError(f"wrong wheel filename: {path.name}")
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = [item.filename for item in infos]
        if len(names) != len(set(names)):
            raise ArtifactContractError("wheel contains duplicate members")
        for name in names:
            member = PurePosixPath(name)
            if member.is_absolute() or ".." in member.parts or "\\" in name:
                raise ArtifactContractError(f"unsafe wheel member: {name}")
            lowered = name.lower()
            if lowered.endswith((".pyc", ".pdb", ".exp", ".lib", ".exe")):
                raise ArtifactContractError(f"unexpected build artifact: {name}")
            if lowered.startswith(("tests/", "spikes/", "tools/", "vendor/")):
                raise ArtifactContractError(f"non-production content in wheel: {name}")

        name_set = set(names)
        required = {suffix: _member_for_suffix(name_set, suffix) for suffix in REQUIRED_SUFFIXES}
        wheel_text = archive.read(required[f"{DIST_INFO}/WHEEL"]).decode("utf-8")
        metadata = archive.read(required[f"{DIST_INFO}/METADATA"]).decode("utf-8")
        entry_points = archive.read(required[f"{DIST_INFO}/entry_points.txt"]).decode("utf-8")
        if (
            "Root-Is-Purelib: false" not in wheel_text
            or "Tag: py3-none-win_amd64" not in wheel_text
        ):
            raise ArtifactContractError("WHEEL metadata is not Windows x64 binary metadata")
        for field in (
            "Version: 1.0.0",
            "Requires-Python: <3.15,>=3.11",
            "License-Expression: MIT",
            "Requires-Dist: budoux==0.9.0",
            "Requires-Dist: numpy==2.4.6",
            "Requires-Dist: Pillow==12.3.0",
        ):
            if field not in metadata:
                raise ArtifactContractError(f"missing METADATA field: {field}")
        if "mojit = mojit.bootstrap:main" not in entry_points:
            raise ArtifactContractError("console entry does not target bootstrap")

        dll = archive.read(required["mojit/_native/win_amd64/libfribidi-0.dll"])
        dll_hash = hashlib.sha256(dll).hexdigest()
        if dll_hash != EXPECTED_DLL_SHA256:
            raise ArtifactContractError(f"FriBiDi hash mismatch: {dll_hash}")
        pe_offset = struct.unpack_from("<I", dll, 0x3C)[0]
        machine = struct.unpack_from("<H", dll, pe_offset + 4)[0]
        optional_magic = struct.unpack_from("<H", dll, pe_offset + 24)[0]
        if dll[:2] != b"MZ" or machine != 0x8664 or optional_magic != 0x20B:
            raise ArtifactContractError("FriBiDi payload is not PE32+ x64")

        record_name = required[f"{DIST_INFO}/RECORD"]
        records = {
            row[0]: row[1]
            for row in csv.reader(archive.read(record_name).decode("utf-8").splitlines())
        }
        if set(records) != name_set:
            raise ArtifactContractError("RECORD inventory does not match wheel members")
        for name in names:
            if name == record_name:
                continue
            algorithm, encoded = records[name].split("=", 1)
            if algorithm != "sha256":
                raise ArtifactContractError(f"unexpected RECORD algorithm for {name}")
            actual = base64.urlsafe_b64encode(hashlib.sha256(archive.read(name)).digest()).rstrip(
                b"="
            )
            if actual.decode("ascii") != encoded:
                raise ArtifactContractError(f"RECORD hash mismatch for {name}")

    return {"wheel": path.name, "members": len(names), "dll_sha256": dll_hash}


def create_deterministic_zip(source: Path, target: Path) -> None:
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(item for item in source.rglob("*") if item.is_file()):
            info = zipfile.ZipInfo(path.relative_to(source).as_posix(), (2026, 8, 23, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes(), compresslevel=9)


def inspect_bundle(path: Path) -> dict[str, object]:
    if not BUNDLE_NAME.fullmatch(path.name):
        raise ArtifactContractError(f"wrong bundle filename: {path.name}")
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ArtifactContractError("bundle contains duplicate members")
        if set(names) != BUNDLE_MEMBERS:
            missing = sorted(BUNDLE_MEMBERS - set(names))
            unexpected = sorted(set(names) - BUNDLE_MEMBERS)
            raise ArtifactContractError(
                f"bundle inventory mismatch; missing={missing}, unexpected={unexpected}"
            )

        manifest_rows: dict[str, str] = {}
        manifest = archive.read("WHEELHOUSE_SHA256SUMS.txt").decode("ascii")
        for line in manifest.splitlines():
            match = re.fullmatch(r"([0-9a-f]{64})  ([^\\/]+)", line)
            if match is None or match.group(2) in manifest_rows:
                raise ArtifactContractError(f"malformed wheelhouse checksum line: {line!r}")
            manifest_rows[match.group(2)] = match.group(1)
        expected_rows = BUNDLE_MEMBERS - {"WHEELHOUSE_SHA256SUMS.txt"}
        if set(manifest_rows) != expected_rows:
            raise ArtifactContractError("wheelhouse checksum inventory mismatch")
        for name, expected in manifest_rows.items():
            if hashlib.sha256(archive.read(name)).hexdigest() != expected:
                raise ArtifactContractError(f"wheelhouse checksum mismatch: {name}")

    return {"bundle": path.name, "members": len(names)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--zip-source", type=Path)
    parser.add_argument("--zip-target", type=Path)
    arguments = parser.parse_args()
    if arguments.wheel is not None:
        print(json.dumps(inspect_wheel(arguments.wheel), sort_keys=True))
        return 0
    if arguments.bundle is not None:
        print(json.dumps(inspect_bundle(arguments.bundle), sort_keys=True))
        return 0
    if arguments.zip_source is not None and arguments.zip_target is not None:
        create_deterministic_zip(arguments.zip_source, arguments.zip_target)
        return 0
    parser.error("provide --wheel, --bundle, or both --zip-source and --zip-target")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
