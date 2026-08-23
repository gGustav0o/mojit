# Phase 4: application orchestration

Status: complete. The verified outcome is recorded in
[PHASE_4_REPORT.md](PHASE_4_REPORT.md).

## Goal

Compose the completed typography and effects layers into a deterministic,
resize-aware animation runtime with bounded mask caching and fixed-step scheduling.

Phase 4 starts with an immutable `PreparedRun` and runtime ports, and ends with
`Frame` values delivered to an injected presenter. It does not implement the
production WezTerm adapter, terminal-state lifecycle, PNG/Kitty transport, or normal
CLI execution.

## Scope

Phase 4 includes:

- one bounded application-owned `TextMask` cache;
- pure fixed-step scheduling calculations;
- minimal structural ports for a monotonic clock and animation backend;
- construction of `TypographyKey`, `RenderContext`, and `EffectConfig` from a
  `PreparedRun`;
- effect lookup and one-frame rendering through the existing registry;
- viewport polling independently of FPS;
- resize-driven mask regeneration;
- late-frame dropping without catch-up bursts;
- cooperative stopping for deterministic tests;
- application dependency, integration, and bounded-resource tests.

## Non-goals

Do not implement in this phase:

- `wezterm cli` subprocess calls or `WEZTERM_PANE` handling;
- terminal alternate-screen, cursor, synchronized-update, or restore behavior;
- PNG encoding, Kitty protocol commands, image IDs, or placement cleanup;
- OS clock wiring or CLI entry into the animation loop;
- `Ctrl+C` policy, exit-code mapping, logging, or traceback presentation;
- async code, threads, queues, background polling, or frame prefetch;
- multi-entry/LRU caches, persistent caches, cache metrics, or locks;
- pause/resume, input handling, effect switching, or runtime configuration changes;
- generic dependency-injection containers, factories, or cross-terminal APIs.

These are shell and transport concerns. Phase 5 will compose the application runtime
with the single production WezTerm backend and own restoration in `finally`.

## Fixed architecture

```text
PreparedRun
    │
    ▼
RenderSession ──► TypographyKey ──► TextMaskCache ──► typography
    │                                      │
    └──────────► RenderContext ────────────┴───────► effect registry ──► Frame
                                                                      │
FixedStepScheduler ◄── MonotonicClock                                 ▼
        │                                                      AnimationBackend
        └──────────────► application runtime ◄── viewport polling
```

Dependency rules:

- `application` may import only `core`, `effects`, and stdlib;
- `application` must not import `adapters`, `config`, or `cli`;
- `core` and `effects` remain unaware of caching, clocks, and runtime ports;
- adapters will satisfy application protocols structurally and therefore do not
  import `application` merely to inherit an interface;
- only the outer runtime loop performs clock, viewport, and presentation effects;
- scheduling math, mask identity, and frame rendering remain independently testable;
- the application runtime never owns terminal restoration.

## Contracts to freeze in `SPEC.md`

Before implementation, make the existing animation requirements exact:

```text
first frame index:       0, due immediately after the initial viewport
frame deadline(n):       started_at + n / fps
render elapsed(n):       n / fps
late work:               skip missed indices; never render a catch-up burst
viewport interval:       0.25 s, independent of FPS
event priority:          due viewport poll before a due frame
initial viewport:        required before scheduling starts
transient poll failure:  retain the last valid viewport
mask cache:              one entry, replaced atomically on a successful miss
```

Wall-clock duration may decide which frame index is due, but it must never be passed
to an effect. Effects receive only the deterministic elapsed value derived from the
selected frame index.

## Runtime ports

Add `src/mojit/application/ports.py` with two small structural protocols:

```python
class AnimationBackend(Protocol):
    def get_viewport(self) -> Viewport | None: ...
    def present(self, frame: Frame) -> None: ...

class MonotonicClock(Protocol):
    def monotonic(self) -> float: ...
    def sleep(self, seconds: float) -> None: ...
```

Port semantics:

- a valid first `Viewport` is mandatory; absence fails before any frame is rendered;
- after initialization, `None` means a transient query failure and retains the last
  valid viewport;
- invalid return types are programming errors, not transient failures;
- backend exceptions propagate unchanged; the production adapter decides which
  viewport failures are recoverable and maps only those to `None`;
- `present` accepts exactly one immutable full-viewport `Frame`;
- monotonic readings must be finite and non-decreasing;
- `sleep` is called only with a finite non-negative duration;
- neither protocol exposes `restore`, terminal state, PNG, or WezTerm details.

Do not mark the protocols runtime-checkable. Behavioral validation belongs at use
sites, while structural typing keeps adapters independent from application code.

## Bounded mask cache

Implement `TextMaskCache` in `src/mojit/application/mask_cache.py` as a single-entry
cache over the existing `TypographyKey` and `TextMask` types.

Required behavior:

1. `get_or_create(key, factory)` returns the stored mask on an equal-key hit;
2. on a miss, it creates exactly one mask and validates that its dimensions equal
   `key.viewport`;
3. the new key/value pair replaces the previous entry only after successful
   creation and validation;
4. a factory exception or invalid result leaves the previous entry intact;
5. `clear()` releases both key and value;
6. the cache never retains history, font bytes, frames, or failure objects.

A single entry is sufficient because one run has one active text/font/orientation and
one current viewport. It also bounds memory when a pane is resized repeatedly. A
resize from A to B and back to A intentionally rasterizes A again instead of retaining
multiple viewport-sized arrays.

## Pure fixed-step scheduler

Implement an immutable `FixedStepScheduler` in
`src/mojit/application/scheduler.py`. It owns arithmetic only; it does not read or
sleep a clock.

Its public operations must cover:

```text
deadline(frame_index)
elapsed_seconds(frame_index)
due_frame_index(now, minimum_index)
delay_until(frame_index, now)
```

Rules:

- `fps` is an integer in `1..60` and `started_at` is finite;
- frame indices are strict non-negative integers;
- `deadline(n) = started_at + n / fps`;
- `elapsed_seconds(n) = n / fps`;
- `due_frame_index` returns `None` before `minimum_index` is due; otherwise it never
  returns an index below that minimum and selects the latest due index when rendering
  is late;
- `delay_until` is clamped to zero;
- no accumulated `deadline += period` drift is used;
- no scheduler method imports `time`, sleeps, mutates state, or renders frames.

The runtime advances its minimum index after each presentation. If rendering frame
`n` makes frames `n+1..m-1` late, it renders `m` once; it does not replay missed
frames.

## Render session

Implement a `RenderSession` in `src/mojit/application/runtime.py` for the pure
composition of one run:

1. accept a validated `PreparedRun`;
2. resolve `effect_id` through `get_effect` at construction, even for manually
   constructed requests;
3. construct one `EffectConfig(seed=request.seed)`;
4. for each viewport, build the exact `TypographyKey` from text, font fingerprint,
   orientation, viewport, and margin;
5. obtain the mask through `TextMaskCache`, using `font_data` only in the rasterizer
   call;
6. construct `RenderContext(viewport, frame_index, frame_index / fps)`;
7. call the resolved effect and validate that the returned frame matches the
   viewport.

Inject the rasterizer as a narrow callable for tests; do not introduce a typography
service interface. The default is the existing `rasterize_text_mask` function.
`RenderSession` holds only the request, renderer/config, rasterizer, and one-entry
cache. It has no clock, adapter, path, config model, terminal state, or frame history.

## Animation loop

Implement one synchronous loop in `src/mojit/application/runtime.py`:

```text
obtain required initial viewport
start monotonic schedule
while not stopped:
    poll viewport when its independent deadline is due
    choose the latest due frame index
    render and present one frame
    sleep until the earlier next frame or viewport-poll deadline
```

Detailed behavior:

1. Query the initial viewport before reading `started_at` and before presentation.
2. Schedule frame `0` at `started_at` and the first poll at
   `started_at + 0.25` seconds.
3. Re-read the clock after rasterization, rendering, presentation, viewport queries,
   and sleep; side-effect duration is therefore accounted for.
4. When poll and frame deadlines are both due, poll first so the frame uses the
   newest valid viewport.
5. Perform at most one viewport query per loop iteration. After lateness, advance the
   poll deadline directly to the first interval boundary after `now`.
6. Keep the last valid viewport on `None`; replace it only with a validated value.
7. A changed viewport naturally changes `TypographyKey` and causes one cache miss.
8. Select the latest due frame at render time, count skipped indices, render once,
   and advance the minimum index.
9. Derive `RenderContext.elapsed_seconds` from that index, never from `now`.
10. Sleep only for the positive duration until the earlier pending event; never use
    busy waiting.
11. Check an optional cooperative stop predicate at stable loop boundaries so fake
    tests can terminate without threads or signals.
12. Let query, typography, effect, presentation, stop-callback, and
    `KeyboardInterrupt` failures propagate. Do not restore terminal state here.

Return a small immutable `AnimationResult` on cooperative completion with only
`presented_frames`, `last_frame_index`, `skipped_frames`, and `viewport_changes`.
`last_frame_index` is `None` when no frame was presented, skipped frames count only
gaps before presented indices, and viewport changes exclude initial acquisition.
This supports diagnostics without retaining masks or frames.

## Work sequence

### P4.0 — Freeze orchestration semantics

1. Add the exact schedule, polling, transient-failure, and cache rules to `SPEC.md`.
2. Record the application ports and shell ownership in `docs/ARCHITECTURE.md`.
3. Add dependency tests prohibiting application imports from adapters/config/CLI and
   prohibiting `time`, subprocess, or terminal access below the runtime ports.

Exit condition: no implementation decision can silently change determinism,
polling cadence, missed-frame policy, or cleanup ownership.

### P4.1 — Bounded mask cache

1. Implement hit, miss, replacement, clear, and result validation.
2. Prove equal keys reuse the exact mask object.
3. Prove viewport changes miss and repeated resize retains only one entry.
4. Prove factory failure and invalid dimensions do not corrupt the prior entry.

Exit condition: typography is reused between frames without unbounded retained
viewport buffers.

### P4.2 — Pure scheduler

1. Implement strict construction and argument validation.
2. Implement absolute deadline and elapsed calculations.
3. Implement latest-due-index selection and clamped delay calculation.
4. Test exact boundaries, early calls, large lateness, maximum FPS, and invalid
   numeric values without real sleeping.

Exit condition: all timing decisions are deterministic functions of explicit
inputs.

### P4.3 — Runtime ports and render session

1. Add the two structural protocols and typed fakes.
2. Resolve the effect once and construct the immutable effect config once.
3. Build the complete typography key and use the one-entry cache.
4. Build exact deterministic render contexts and validate output dimensions.
5. Test unknown effects, same-viewport reuse, resize misses, and frame-index/elapsed
   propagation.

Exit condition: `PreparedRun + Viewport + frame_index -> Frame` works in memory with
one rasterization per active typography key.

### P4.4 — Resize-aware animation loop

1. Implement required initial viewport acquisition.
2. Combine independent poll and frame deadlines in one synchronous event loop.
3. Implement transient failure retention, resize switching, missed-frame dropping,
   and cooperative stopping.
4. Test all paths with scripted clocks and in-memory backends; use no wall-clock
   timing assertions.
5. Prove all exceptions and `KeyboardInterrupt` propagate without hidden retries or
   restoration.

Exit condition: the loop schedules, polls, renders, and presents deterministically
without production I/O.

### P4.5 — Integrated and longevity gate

Exercise the full application path over:

1. low and high FPS;
2. stable viewport, resize, and transient poll failure sequences;
3. fast frames and frames that overrun multiple deadlines;
4. horizontal and vertical requests;
5. all four registered effects;
6. thousands of fake-clock frames and resize events.

Assert exact frame indices and elapsed values, output dimensions, polling bounds,
cache-call counts, no catch-up bursts, no retained frame history, and constant cache
size. Synthetic tests must not depend on WezTerm, installed fonts, Raqm, or real time.

Exit condition: long-running orchestration has bounded application-owned state and
stable deterministic behavior.

### P4.6 — Documentation and phase report

1. Update `SPEC.md` and `docs/ARCHITECTURE.md` with implemented behavior only.
2. Record unit, integration, longevity, coverage, lint, format, compile, and
   dependency results in `docs/PHASE_4_REPORT.md`.
3. Update README to point to the completed phase and the production shell boundary.

Exit condition: documentation matches tested behavior without claiming production
terminal support.

## Planned file layout

```text
src/mojit/application/ports.py
src/mojit/application/mask_cache.py
src/mojit/application/scheduler.py
src/mojit/application/runtime.py

tests/unit/application/test_ports.py
tests/unit/application/test_mask_cache.py
tests/unit/application/test_scheduler.py
tests/unit/application/test_runtime.py
tests/integration/test_application_pipeline.py
tests/integration/test_application_longevity.py
```

Existing core, effect, config, and adapter modules should not move. If a test needs
control over time, viewport, rasterization, or presentation, use a narrow in-memory
fake at the application boundary.

## Required checks

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m pytest --cov=mojit.application `
  --cov-fail-under=95
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m ruff format --check src tests
.\.venv\Scripts\python.exe -m compileall -q src tests
```

All scheduler and runtime tests use fake time. They must be deterministic,
system-independent, and non-skipping.

## Phase gate

Phase 4 is complete only when:

- the cache key contains every typography-affecting value and the cache retains at
  most one mask;
- failed cache creation cannot evict a valid entry;
- absolute scheduling starts at frame `0` and derives elapsed time only from index;
- lateness skips frame indices without catch-up presentation bursts;
- viewport polling is independent of FPS and bounded to approximately four queries
  per scheduled second;
- initial viewport absence fails before presentation and transient later absence
  keeps the last valid viewport;
- resize causes exactly one new mask for the new active key;
- application code depends on structural ports, not concrete adapters;
- the runtime retains no frame history and remains bounded in longevity tests;
- runtime failures propagate for the outer Phase 5 restoration shell;
- full tests, focused coverage, lint, format, compile, dependency, and documentation
  checks pass;
- no WezTerm subprocess, terminal state, PNG, Kitty, restore, or CLI-loop behavior
  leaks into the phase.

## Implementation increments

Keep commits independently reviewable:

1. SPEC/architecture contracts and bounded mask cache;
2. pure fixed-step scheduler;
3. structural ports and render session;
4. resize-aware animation loop;
5. integrated longevity gate and phase report.

## Follow-up boundary

Phase 5 will implement and verify the concrete WezTerm backend, monotonic clock
adapter, PNG/Kitty presentation, terminal-state lifecycle, idempotent restoration,
`Ctrl+C` handling, CLI wiring, and injected-failure cleanup. It will consume the
Phase 4 ports without moving WezTerm policy into application or rendering code.
