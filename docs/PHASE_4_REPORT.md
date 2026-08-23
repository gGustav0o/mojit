# Phase 4 report

- Status: Complete
- Date: 2026-08-23
- Scope: bounded application orchestration

## Delivered

| Area | Result |
|---|---|
| Runtime ports | Structural `AnimationBackend` and `MonotonicClock` protocols |
| Mask cache | Atomic single-entry `TypographyKey -> TextMask` cache |
| Scheduler | Immutable absolute-deadline fixed-step calculations |
| Render session | `PreparedRun + Viewport + frame_index -> Frame` composition |
| Animation loop | Independent 250 ms viewport polling and frame presentation |
| Resize | Last-valid viewport retention and key-driven mask regeneration |
| Lateness | Latest-due frame selection without catch-up bursts |
| Diagnostics | Bounded immutable completion counters in `AnimationResult` |
| Boundaries | Static tests reject shell adapters and OS I/O from application |

`RenderSession` resolves the effect once, constructs one immutable `EffectConfig`,
and owns one `TextMaskCache`. It retains no frame history. The synchronous runtime
owns only counters, current viewport, deadlines, and the next frame index.

## Verified scheduling behavior

```text
frame 0:             due at started_at
deadline(n):         started_at + n / fps
effect elapsed(n):   n / fps
late frames:         skipped, never replayed
viewport polling:    every 0.25 scheduled seconds, independent of FPS
deadline priority:   viewport poll before frame rendering
poll lateness:       one query, then advance to the first future boundary
```

All timing tests use scripted monotonic clocks. No test waits on wall-clock time.
Transient `None` viewport samples retain the previous valid viewport; invalid values
and collaborator exceptions propagate to the future outer restoration shell.

## Bounded-state evidence

The longevity gate presented 1,000 deterministic frames at 60 FPS while alternating
viewport dimensions on every scheduled poll. It verified:

- no skipped frames under a zero-cost fake backend;
- exactly one rasterization per active key change;
- one current mask retained by application cache;
- one last frame retained by the fake backend;
- no frame or viewport history accumulated by runtime.

## Gate results

```text
pytest:                    376 passed
application coverage:     97.30% (required >= 95%)
ruff check:                passed
ruff format --check:       passed
compileall:                passed
dependency gate:           passed
longevity gate:            1,000 frames passed
system-dependent skips:    0
```

## Deferred by design

- concrete `wezterm cli` viewport acquisition;
- production monotonic clock adapter;
- PNG encoding and Kitty graphics transport;
- alternate screen, cursor, synchronized update, and image cleanup;
- idempotent terminal restoration in `finally`;
- `Ctrl+C`, exit-code mapping, debug logging, and CLI runtime wiring.

These are Phase 5 shell and transport responsibilities. They will consume the Phase
4 structural ports without moving WezTerm policy into application or rendering code.
