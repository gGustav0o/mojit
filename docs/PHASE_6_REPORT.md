# Phase 6 report: reproducible Windows distribution

Status: complete.

## Result

`mojit 1.0.0` is packaged as `py3-none-win_amd64` under MIT. The canonical local
release consists of the platform wheel and an offline wheelhouse for CPython
3.11-3.14 x64. Nothing was published or signed.

The entry points now share one bootstrap. Before CLI/Pillow import it enables secure
Windows DLL search, registers only the installed package directory, loads the bundled
FriBiDi by absolute path, and retains both handles. It never scans or mutates `PATH`.
A hostile same-named DLL at the start of `PATH` is explicitly covered by the installed
matrix.

## Native provenance

```text
FriBiDi:       1.0.16 / v1.0.16
source SHA256: 1b1cde5b235d40479e91be2f0e88a309e3214c8ab470ec8a2744d82a5a9ea05c
binary SHA256: 4283ba30461395fdf46399b2665176e6f41d11bc7bf6977188120152fde31fd2
target:        PE32+ x64
compiler:      MSVC 19.51.36252
linker:        LINK 14.51.36252.0
Meson/Ninja:   1.12.0 / 1.13.2
license:       LGPL-2.1-or-later
```

Two clean build directories produced the same DLL byte-for-byte with `/Brepro`.
`dumpbin` verified the required exports and only the declared Windows/UCRT runtime
dependencies. The complete upstream source archive, license, reproduction script,
and manifest are versioned with the project.

## Artifacts

Final local hashes:

```text
1b1cde5b235d40479e91be2f0e88a309e3214c8ab470ec8a2744d82a5a9ea05c  fribidi-1.0.16.tar.xz
fda34183e61f553a9c0e891c5e29b1ed999cd1fc7e9614344d930bf729143fb7  mojit-1.0.0-py3-none-win_amd64.whl
4789ec2f4960100e7f5328f23c6555d63cf02ca7c5297109de27eb9ce08e8223  mojit-1.0.0-windows-x64-wheelhouse.zip
4764365d7fbca9f9bdd6833e4b7e21cbc6fae1312ff53e13ffe9dffa11653782  THIRD_PARTY_NOTICES.md
```

Two final wheel builds with fixed `SOURCE_DATE_EPOCH` independently produced the
same wheel SHA-256. Closed-world inspection verified the filename, WHEEL/METADATA,
entry point, license files, exact native payload, safe member paths, executable
allowlist, and every RECORD hash. Tests, spikes, tools, caches, and debug artifacts
are absent.

## Installed matrix

`verify_artifacts.ps1` installed only from the generated wheelhouse with user site
disabled and a sanitized child `PATH`. Each cell passed console/module smoke,
hostile-shadow resolution, Raqm, vertical CJK rendering, missing font/native failure,
uninstall, and offline reinstall:

| CPython | FriBiDi loaded from package | Vertical reference SHA-256 |
|---|---|---|
| 3.11.16 | yes | `4999a16da1fc92a1a914b239ea2efd64f7f0219017142b6a2eec9b3dc49fe262` |
| 3.12.14 | yes | `4999a16da1fc92a1a914b239ea2efd64f7f0219017142b6a2eec9b3dc49fe262` |
| 3.13.15 | yes | `4999a16da1fc92a1a914b239ea2efd64f7f0219017142b6a2eec9b3dc49fe262` |
| 3.14.7 | yes | `4999a16da1fc92a1a914b239ea2efd64f7f0219017142b6a2eec9b3dc49fe262` |

The interpreters and venvs were uv-managed and isolated under ignored `build/` on the
reference Windows 11 host. Actual loaded-module enumeration proved that the only
`libfribidi-0.dll` came from each venv's installed `mojit/_native/win_amd64`.

## Installed WezTerm acceptance

Environment:

```text
OS:       Microsoft Windows NT 10.0.26200.0
WezTerm:  20240203-110809-5046fc22
CPython:  3.13.15 installed matrix cell
Pillow:   12.3.0
NumPy:    2.4.6
Raqm:     0.10.5
FriBiDi:  bundled 1.0.16
Font:     C:/Windows/Fonts/YuGothB.ttc
```

The installed live suite passed horizontal and vertical CJK, injected runtime
failure, repeated cleanup, four resizes, and a 300-second structured workload:

| Metric | Value |
|---|---:|
| Result | `4 passed in 302.91s` |
| Frames | 6,147 |
| Average / maximum presentation | 4.738 / 188.214 ms |
| Terminal bytes | 477,966,737 |
| Maximum write | 4,158 bytes |
| Resize attempts / detected changes | 4 / 4 |
| WezTerm working-set delta | +13,758,464 bytes |

The final wheel also passed a 5-second installed live run: `4 passed`, 82 frames,
4/4 resizes, exit `0`. A separate
production-command run received a real Ctrl+C through WezTerm, returned exit `0`, and
left the pane on the primary screen with a visible cursor. All disposable panes were
closed afterward.

## Source and release gates

```text
pytest:                    499 passed
coverage:                  96.72% (required 95%)
ruff check:                passed
ruff format --check:       passed
compileall:                passed
FriBiDi double build:      byte-identical
wheel double build:        byte-identical
artifact/matrix verifier:  passed, CPython 3.11-3.14
installed WezTerm:         passed
```

Reproduction entry points:

```powershell
.\tools\release\build_fribidi.ps1
.\tools\release\build_artifacts.ps1
.\tools\release\verify_artifacts.ps1
```

Artifacts remain under ignored `dist/release/`. Publication, signing, installer work,
and credentials require separate explicit authorization.
