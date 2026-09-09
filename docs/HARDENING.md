# Scene-engine hardening and release evidence

Status: release-ready `1.1.0` candidate, audited through 2026-09-09.

This document records the independent review of the Phase 7-11 implementation. It is
not a replacement for the v1 compatibility contract in `SPEC.md` or the sequencing
in `ROADMAP.md`. No tag or GitHub release was created.

## Verified findings and disposition

1. **Hosted source CI initially failed — fixed and green.** On a clean GitHub runner,
   `Get-Command python` returned multiple applications and PowerShell converted the
   resulting `Source` array into an invalid newline-separated command path. Command
   resolution now selects one application deterministically. CPython 3.11 also uses
   different argparse alias/metavar layout and wrapped a hyphenated help phrase; the
   semantic help test and copy now support readable output on both endpoints. Hosted
   run `34264515034` passed the complete gate on Windows CPython 3.11 and 3.14.
2. **Tracked archive garbage — fixed and mechanically guarded.** `mojit.rar` is gone.
   The source gate rejects present tracked files under `build/` or `dist/`, plus
   tracked RAR, ZIP, 7z, or wheel release artifacts. No such path is tracked.
3. **Scene composition retained avoidable full-frame data — fixed.** Layer output is
   streamed in exact back-to-front order through Pillow source-over composition, so
   ownership of layer contributions does not scale with the configured layer count.
   Mutable or uncertain caller arrays are still isolated; a provably immutable
   bytes-backed compositor result is adopted without a second full-frame copy.
   Semantic tests cover z-order, alpha, transparent-RGB canonicalization, deterministic
   replay, one-layer identity, and mutable-source isolation.
4. **Resource bounds remain explicit and observable.** Configuration accepts at most
   16 layers and every procedural layer caps its generated field at 4,096 particles.
   The 16-layer 960×540 integration test observes prior layer buffers at the layer
   boundary and verifies that at most one remains live, rather than asserting a
   private compositor implementation detail. Large viewports still allocate by pixel
   area, but do not accidentally retain every full-frame contribution.
5. **Renderer process longevity evidence was missing — fixed.** The standalone soak
   now samples the actual Python process, reports initial and post-warm-up memory,
   sample peaks, final memory, latter-half slopes, and the Windows OS working-set
   high-water mark. The live soak separately records renderer and terminal memory.
   Harness tests validate PID and metric behavior without inventing a flaky
   short-window leak threshold.
6. **Installed checks were narrower than source behavior — fixed.** The isolated wheel
   gate covers help, legacy effect listing, scene listing, strict scene configuration,
   deterministic non-interactive rendering, every built-in scene, runtime metadata,
   native payload, and checkout-independent execution. The full offline release
   matrix also checks the hostile-PATH DLL case, missing font/native failures,
   uninstall/reinstall, and current-user installer install/upgrade/uninstall.
7. **Release version data was duplicated and stale — fixed.** The compatible additive
   release is prepared as `1.1.0`. Root `VERSION` is authoritative for package
   metadata, artifact contracts/names, build verification, and installer discovery.
   Historical `1.0.0` references describing the original v1 contract remain intact.
8. **Live resize instructions allowed a false environmental failure — fixed.** A
   single-pane tab accepts WezTerm resize commands without changing geometry. The
   installed live helper now fails before testing unless its disposable target has
   both horizontal and vertical split boundaries.

## Automated verification evidence

- `tools/verify.ps1`: 673 non-graphical tests passed, 97.19% coverage; Ruff lint and
  format, bytecode compilation, source discovery, wheel build, isolated install, help,
  effects, scenes, configuration, deterministic render, and Git hygiene passed.
- GitHub Actions run `34264515034`: Windows CPython 3.11 and 3.14 jobs both passed the
  same source gate.
- `tools/release/build_artifacts.ps1`: produced and validated
  `mojit-1.1.0-py3-none-win_amd64.whl` and the deterministic offline wheelhouse bundle.
- `tools/release/verify_artifacts.ps1 -SkipPythonInstall`: fresh offline wheel installs
  and all installed probes passed on CPython 3.11.16, 3.12.14, 3.13.15, and 3.14.7;
  the current-user installer workflow passed on CPython 3.13.

## Process-memory evidence

Both runs used the actual renderer process and ten-second samples after warm-up.
Values below are bytes.

| Run | Metric | Initial | Post-warm-up | Sample peak | Final | OS peak |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `rainy-night`, 930×667, 600 s, 10,978 frames | Working set | 42,262,528 | 44,355,584 | 49,438,720 | 44,818,432 | 61,726,720 |
| same | Private bytes | 532,439,040 | 532,676,608 | 538,578,944 | 533,790,720 | n/a |
| 16 layers, 1920×1080, 600 s, 1,735 frames | Working set | 45,219,840 | 54,161,408 | 65,384,448 | 57,085,952 | 113,127,424 |
| same | Private bytes | 535,449,600 | 542,998,528 | 555,216,896 | 546,922,496 | n/a |

Representative latter-half slopes were +3,195 working-set bytes/s and +7,300 private
bytes/s. Stress slopes were +8,087 and +12,018 bytes/s. Stress samples settled into
repeating allocation bands near the end rather than accelerating, and final values
dropped below sampled peaks. These finite runs show no sustained runaway growth, but
small positive slopes and allocator high-water retention mean they do not prove
general leak freedom.

## Live WezTerm evidence

- In a 1890×1012 landscape pane, eight bounded cases passed: horizontal/vertical CJK
  at 8 and 15 FPS, `rainy-night`, `snowfall`, and `space`, plus injected runtime
  failure with repeated restoration. The initial structured resize case then failed
  honestly because that full-size pane had no movable split boundary; this led to the
  helper preflight above and is not counted as a product pass.
- All three built-in scenes passed again in a 940×1012 portrait pane (3 passed in
  5.71 s).
- In a disposable pane with two movable boundaries, the 60.08-second `rainy-night`
  resize soak passed: 476 frames, 7.92 achieved FPS against target 8, four skipped
  opportunities, and four observed changes across 940×506, 980×506, 940×506,
  940×598, and 940×506. Cursor restoration passed.
- A real Ctrl+C sent to the isolated CPython 3.14 wheel installation returned exit
  code 0, and WezTerm reported the cursor visible afterward.

## Evidence boundaries and residual risk

- Hosted CI exercises supported-range endpoints (3.11 and 3.14); the fuller 3.11-3.14
  artifact matrix is local evidence, not a hosted-matrix claim.
- Ten-minute process samples are meaningful longevity evidence, not a mathematical
  proof that every Python/Pillow/NumPy/native allocation is leak-free indefinitely.
- Full-viewport immutable rendering necessarily scales with pixel area. Layer and
  particle amplification are capped, while `Viewport` remains caller-provided so
  offline rendering is not tied to an arbitrary monitor-size policy.
- Scene configuration version 1 intentionally requires one text layer under ADR 0009.
  A richer or text-free user representation belongs in a future configuration
  version; version 1 semantics must not be silently changed.
- Windows + WezTerm is the supported release target. Native Kitty-terminal support
  was not implemented or implied by this hardening work.
