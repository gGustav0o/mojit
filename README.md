# mojit

`mojit` is a Windows 11 / WezTerm CLI for displaying large animated Unicode text.

The product requirements are in [SPEC.md](SPEC.md), and dependency boundaries are
recorded in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

Phase 0 results and decisions are summarized in
[docs/PHASE_0_REPORT.md](docs/PHASE_0_REPORT.md). Phase 1's deterministic typography
core is complete; see [the plan](docs/PHASE_1_PLAN.md) and
[the report](docs/PHASE_1_REPORT.md). Phase 2's configuration and input boundary is
also complete; see [the plan](docs/PHASE_2_PLAN.md) and
[the report](docs/PHASE_2_REPORT.md). Experimental code remains isolated under
`spikes/`. Phase 3's pure compositor and deterministic effects are complete; see
[the plan](docs/PHASE_3_PLAN.md) and [the report](docs/PHASE_3_REPORT.md). Phase 4's
bounded application orchestration is complete; see [the plan](docs/PHASE_4_PLAN.md)
and [the report](docs/PHASE_4_REPORT.md). Phase 5's production WezTerm transport and
terminal lifecycle are complete; see [the report](docs/PHASE_5_REPORT.md). Phase 6's
reproducible Windows distribution is also complete; see
[the plan](docs/PHASE_6_PLAN.md) and [the report](docs/PHASE_6_REPORT.md).

## Runtime prerequisites

- Windows 11 and WezTerm;
- CPython 3.11-3.14 x64;
- the verified Phase 6 wheelhouse (BudouX, Pillow/Raqm, and FriBiDi are self-contained
  there);
- a CJK font. The v1 default is `C:/Windows/Fonts/YuGothB.ttc`.

## Install from the local release candidate

```powershell
Expand-Archive .\dist\release\mojit-1.0.0-windows-x64-wheelhouse.zip .\wheelhouse
py -3.13 -m venv .venv-mojit
.\.venv-mojit\Scripts\python.exe -m pip install --no-index --find-links .\wheelhouse mojit==1.0.0
.\.venv-mojit\Scripts\mojit.exe --list-effects
```

Use the same install command with `--upgrade` to reinstall. Uninstall with:

```powershell
.\.venv-mojit\Scripts\python.exe -m pip uninstall mojit
```

Verify release-file hashes against `dist/release/SHA256SUMS.txt` before installation.
The wheel is Windows x64 only and loads its packaged FriBiDi by absolute path; it does
not scan or modify `PATH`.

Run from an interactive WezTerm pane:

```powershell
mojit "電脳世界"
mojit "電脳世界" --vertical --effect glitch
mojit "警告" --fps 15
```

`--fps` is a target presentation and effect-sampling rate in the range `1..15`; the
default is `8`. Late frame indices are skipped rather than replayed, so the achieved
rate can be lower when rendering or terminal output is expensive.

`Ctrl+C` stops the continuous animation and restores the primary screen, cursor, and
terminal attributes. Piped UTF-8 text is supported. Redirecting run-mode stdout is not.

If the process is hard-terminated or terminal output is already broken, cleanup bytes
cannot be delivered. Close the affected pane to recover its terminal state.

## Reproduce and verify

```powershell
.\tools\release\build_fribidi.ps1
.\tools\release\build_artifacts.ps1
.\tools\release\verify_artifacts.ps1
```

The project is MIT-licensed. FriBiDi remains LGPL-2.1-or-later and separately
replaceable; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
