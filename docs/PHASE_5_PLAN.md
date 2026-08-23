# Phase 5: production WezTerm shell

Status: complete.

## Goal

Connect the completed application runtime to one production WezTerm backend and make
the normal CLI render continuously, react to resize, stop on `Ctrl+C`, and restore
all terminal state after success, interruption, or failure.

Phase 5 starts with `PreparedRun`, the Phase 4 runtime ports, and accepted Phase 0
ADRs. It ends with a source checkout that runs the v1 command in WezTerm. Release
artifact construction and FriBiDi distribution remain a separate packaging gate.

## Scope

Phase 5 includes:

- bounded exact-pane discovery through `wezterm cli list --format json`;
- validated WezTerm pane geometry in pixels and cells;
- deterministic PNG encoding through Pillow;
- direct chunked Kitty Graphics Protocol commands;
- one stable process-owned image ID and replacement placement;
- alternate-screen, cursor, synchronized-update, and image lifecycle;
- idempotent restoration after partial startup, failures, and `KeyboardInterrupt`;
- a stdlib monotonic clock adapter;
- CLI composition of `PreparedRun`, backend, clock, and `run_animation`;
- offline failure-matrix tests and live disposable-pane acceptance tests;
- production runtime and cleanup documentation.

## Non-goals

Do not implement in this phase:

- terminals other than WezTerm or a generic terminal-backend hierarchy;
- a `wezterm imgcat` subprocess frame path;
- iTerm2, zlib-RGBA, sixel, GPU, or shader transports;
- async I/O, threads, background polling, queues, or frame buffering;
- multiple images, placements, panes, or dynamic effect switching;
- adaptive FPS, delta encoding, PNG optimization heuristics, or transport metrics;
- new CLI/config options, hidden failure-injection flags, or a TUI;
- reading terminal replies from stdin;
- recovery guarantees after hard process termination or a broken output channel;
- FriBiDi bundling, wheel/installer creation, signing, or clean-Windows release CI;
- new third-party runtime dependencies.

## Fixed architecture

```text
cli composition root
  ├── prepare_run() ───────────────────────────────► PreparedRun
  ├── SystemMonotonicClock ────────────────────────► MonotonicClock port
  └── WezTermBackend ──────────────────────────────► AnimationBackend port
          ├── viewport.py ──► bounded wezterm CLI subprocess
          ├── png_encoder.py ──► Pillow PNG
          ├── kitty_protocol.py ──► pure escape-command chunks
          └── terminal_state.py ──► binary stdout lifecycle

PreparedRun + backend + clock ──► application.run_animation()
```

Dependency rules:

- `application` remains unchanged and imports no adapter, CLI, subprocess, or clock;
- `adapters.wezterm` may import core models, Pillow, and stdlib only;
- the WezTerm adapter satisfies Phase 4 protocols structurally and never imports
  them merely for inheritance;
- `kitty_protocol.py` and JSON parsing are pure and perform no I/O;
- only `viewport.py` starts `wezterm cli`;
- only `terminal_state.py` writes terminal-control bytes;
- only `png_encoder.py` invokes the image codec;
- `backend.py` composes these operations but owns no layout, effect, scheduling, or
  CLI policy;
- `cli.py` is the only production composition root and owns exit-code policy.

No abstract factory or dependency-injection container is introduced. Tests inject
narrow callables and in-memory streams at existing side-effect boundaries.

## Production preflight contract

Preflight must finish before the first terminal mutation:

1. `PreparedRun` is fully assembled, including font/Raqm checks and effect lookup.
2. stdout is an interactive terminal with a binary write/flush path.
3. `WEZTERM_PANE` exists and is a strict non-negative decimal pane ID.
4. one bounded `wezterm cli list --format json` call succeeds.
5. exactly one returned record matches the target pane and contains valid positive
   rows, columns, pixel width, and pixel height.
6. the initial geometry is cached for the first runtime `get_viewport()` call.

For v1, successful exact-pane WezTerm CLI discovery is the bounded transport
capability proof. Do not emit a Kitty query and read a reply from stdin: stdin may
contain the user's piped text and is reserved exclusively for input. Record this
clarification in ADR 0001 before implementation.

`TERM_PROGRAM` and DPI may be recorded for debug diagnostics but are not layout or
identity inputs. No minimum WezTerm version is invented without separate evidence.

Preflight errors are actionable and occur before alternate-screen entry. They include
missing/invalid pane ID, non-interactive output, missing executable, timeout,
non-zero subprocess status, oversized/invalid JSON, absent/duplicate pane, and invalid
geometry.

## Viewport adapter

Add `src/mojit/adapters/wezterm/viewport.py` with a frozen private transport model:

```text
PaneGeometry
  pane_id:       int
  viewport:      Viewport
  columns:       int
  rows:          int
  dpi:           finite positive float | None
```

Required behavior:

- command: `wezterm cli list --format json` with `shell=False` semantics;
- timeout: two seconds;
- stdout: strict UTF-8 and at most 1 MiB before JSON parsing;
- root JSON value: list;
- target match: exactly one record whose `pane_id` equals `WEZTERM_PANE`;
- `size`: mapping with strict positive integer `rows`, `cols`, `pixel_width`, and
  `pixel_height`; booleans are rejected;
- DPI is validated for diagnostics but never enters `Viewport` or layout; WezTerm's
  observed `0` unknown-DPI sentinel is normalized to `None`;
- stderr included in errors only as a bounded sanitized excerpt;
- no current working directory, shell command string, stdin, or terminal replies are
  used.

The backend caches a successful preflight geometry. Its first `get_viewport()`
returns that viewport without another subprocess. Later successful polls replace the
complete geometry even when only rows/columns changed. Expected runtime query
failures return `None` and retain the last geometry; unexpected programming errors
propagate.

## PNG encoding

Add `src/mojit/adapters/wezterm/png_encoder.py` with one pure function:

```text
encode_frame_png(frame: Frame) -> bytes
```

Contract:

- accept only an immutable full-viewport `Frame`;
- preserve exact RGBA dimensions and bytes;
- use Pillow's PNG encoder with fixed `compress_level=1`, matching Phase 0 evidence;
- return one complete non-empty PNG payload;
- produce identical bytes for identical frames in the pinned environment;
- never mutate the frame, retain buffers, write files, or expose Pillow objects.

PNG encoding is once per presented frame. No custom codec, zlib-RGBA fallback, or
content-dependent tuning is added.

## Kitty protocol encoder

Implement `src/mojit/adapters/wezterm/kitty_protocol.py` as pure validated byte
encoding.

Freeze these v1 values:

```text
action:                  a=T
format:                  f=100 (PNG)
quiet successful reply: q=1
cursor movement:         C=1
image identity:          one positive 31-bit process-owned ID
pixel size:              s=<width>,v=<height>
cell placement:          c=<columns>,r=<rows>
base64 chunk size:       4096 bytes
continuation:            m=1, final m=0
terminator:              ESC \
```

The first command contains all controls and the first payload chunk. Continuation
commands contain only `m`. Expose an iterator of bounded command chunks instead of
concatenating a second multi-megabyte escape buffer. Base64 chunk size must remain a
positive multiple of four.

Deletion is exact and quiet:

```text
ESC_Ga=d,d=I,i=<image_id>,q=1 ESC\
```

Use one image ID for the process lifetime. Derive the production default through a
pure `make_image_id(process_id)` function using the `0x4D000000` namespace plus the
low 24 PID bits; allow explicit injection in tests. Never use randomness or a global
mutable ID allocator.

## Terminal lifecycle

Implement `src/mojit/adapters/wezterm/terminal_state.py` around an injected binary
stream. It does not close the stream.

Entry sequence:

```text
alternate screen on
clear screen
cursor home
cursor hidden
flush
```

Presentation sequence:

```text
synchronized update on
cursor home
Kitty image command chunks
synchronized update off
flush once
```

Restore sequence:

```text
synchronized update off
delete owned image and placement
cursor visible
alternate screen off
flush
```

Lifecycle rules:

- mark cleanup as required before writing the first entry byte;
- presentation is legal only while active;
- a presentation failure may leave synchronized-update mode uncertain, so restore
  always begins by disabling it;
- successful restore makes subsequent restore calls no-ops;
- failed restore remains retryable and is never reported as successful;
- restore after partial entry attempts the full safe cleanup sequence;
- terminal entry cannot occur twice on one session;
- no cleanup sequence is promised after `TerminateProcess`, power loss, or a
  physically broken stream; closing the affected pane is the documented recovery.

All escape constants and state transitions receive exact byte-level tests.

## WezTerm backend

Implement `WezTermBackend` in `src/mojit/adapters/wezterm/backend.py` as the concrete
composition of viewport source, PNG encoder, Kitty encoder, and terminal lifecycle.

Public shell operations:

```text
preflight() -> None
enter() -> None
get_viewport() -> Viewport | None
present(frame: Frame) -> None
restore() -> None
```

Behavior:

1. `preflight` performs and caches the required initial geometry without mutation.
2. `enter` requires successful preflight and activates terminal state.
3. the first runtime viewport request consumes the cached geometry.
4. later polls update the complete geometry or return `None` on an expected transient
   query failure.
5. `present` requires active state and a geometry whose pixel dimensions match the
   frame.
6. `present` encodes PNG once, streams one synchronized Kitty replacement, and
   retains neither frame nor payload.
7. `restore` delegates idempotent cleanup using the same image ID.

Rows/columns belong only to placement. Pixel viewport belongs only to layout and
frame validation. A cell-only resize updates placement without forcing a text-mask
miss.

Define a small adapter exception hierarchy that distinguishes preflight/environment,
viewport-query, protocol/encoding, terminal-output, and lifecycle failures. Do not
catch `BaseException` inside the adapter.

## Clock and CLI composition

Add `src/mojit/adapters/clock.py` with `SystemMonotonicClock` backed only by
`time.perf_counter()` and `time.sleep()`.

Normal CLI order:

```text
parse and prepare request
construct backend and clock
backend preflight
enter terminal
run_animation(request, backend, clock)
restore terminal
map completion or failure to exit status
```

Freeze exit behavior:

| Outcome | Restore | Exit |
|---|---|---:|
| `--help`, `--list-effects`, cooperative completion | not entered / successful | 0 |
| `KeyboardInterrupt` | successful | 0 |
| CLI/config/font/preflight environment error | not entered | 2 |
| runtime, PNG, protocol, viewport bug, or output failure | attempted | 1 |
| any cleanup failure, including after interrupt | failed | 1 |
| primary failure plus cleanup failure | both retained in diagnostic | 1 |

The shell must not let a cleanup exception silently erase the primary failure. Use a
small combined lifecycle error containing both causes when necessary. Tracebacks
remain debug-only. Default `Ctrl+C` prints no traceback and is the normal way to stop
an unbounded animation.

No normal text is written to stdout during run mode. Error reporting occurs only
after restoration and goes to stderr. `--list-effects` remains isolated from config,
font, WezTerm, terminal state, PNG, and clock work.

## Failure matrix

Automated tests must cover every mutation boundary:

| Point | Expected result |
|---|---|
| request preparation fails | no backend construction or terminal bytes |
| preflight fails | no terminal bytes |
| entry write/flush fails | restore attempted |
| initial runtime viewport unavailable unexpectedly | restore attempted, exit 1 |
| runtime poll timeout/malformed response | last geometry retained |
| rasterizer/effect/PNG/protocol fails | restore attempted, exit 1 |
| presentation fails before/inside/after synchronized update | restore attempted |
| `KeyboardInterrupt` during render/present/sleep | restore succeeds, exit 0 |
| restore fails after success/interrupt/failure | exit 1 with both causes retained |
| restore called twice after success | no additional output, no error |

Use scripted subprocess results, fake clocks, failing binary streams, and injected
callables. Offline tests never invoke WezTerm, sleep in real time, or mutate a real
terminal.

## Work sequence

### P5.0 — Freeze shell contracts

1. Add exact preflight, byte protocol, state transitions, exit codes, and combined
   failure policy to `SPEC.md`.
2. Clarify ADR 0001's bounded capability check without reading stdin.
3. Update `docs/ARCHITECTURE.md` with adapter composition and lifecycle ownership.
4. Add dependency tests for application/adapter/CLI directions.

Exit condition: startup, mutation, cleanup, and error ownership are unambiguous.

### P5.1 — Pure PNG and Kitty encoders

1. Implement strict PNG frame encoding.
2. Implement validated streaming Kitty transmission and exact deletion commands.
3. Implement pure process image-ID derivation.
4. Test single/multiple chunks, base64 reconstruction, exact controls, invalid
   numbers, deterministic PNG bytes, and input preservation.

Exit condition: `Frame + geometry + image ID` produces exact bounded command chunks
without I/O.

### P5.2 — Bounded viewport acquisition

1. Implement environment pane-ID parsing and pure JSON geometry parsing.
2. Implement the timeout-bounded no-shell subprocess call and output limits.
3. Implement exact target selection and strict geometry validation.
4. Test timeout, missing executable, non-zero status, invalid UTF-8/JSON, oversized
   output, missing/duplicate pane, bad fields, and valid resize sequences.

Exit condition: one explicit call returns one trusted `PaneGeometry` or one typed
actionable error.

### P5.3 — Terminal state machine

1. Implement entry, synchronized presentation, and restore sequences.
2. Make successful cleanup idempotent and failed cleanup retryable.
3. Test partial writes and flush failures at every transition.
4. Prove the stream is not closed and no frame/payload history is retained.

Exit condition: every reachable mutated state has one tested cleanup path.

### P5.4 — Concrete backend

1. Compose preflight geometry, terminal state, PNG, and Kitty operations.
2. Return the cached initial viewport exactly once.
3. Retain geometry across expected transient poll failures.
4. Update cell placement independently from pixel-mask invalidation.
5. Validate frame/geometry compatibility before emitting presentation bytes.

Exit condition: the backend structurally satisfies Phase 4 runtime behavior without
importing application.

### P5.5 — Clock and CLI shell

1. Add the stateless stdlib monotonic clock adapter.
2. Replace the CLI runtime placeholder with production composition.
3. Guarantee preflight-before-entry and restore-after-entry ordering.
4. Implement normal interrupt and combined primary/cleanup failure policy.
5. Preserve existing help, list-effects, input, debug, and exit-code behavior.

Exit condition: `mojit "電脳世界"` reaches the application loop only after complete
safe preflight and always attempts cleanup after mutation.

### P5.6 — Offline integration and failure gate

1. Exercise `CLI -> PreparedRun -> runtime -> fake WezTerm backend` end to end.
2. Exercise `Frame -> PNG -> Kitty chunks -> binary stream` and decode the emitted
   PNG back to exact RGBA.
3. Run the complete failure matrix, including cleanup failures paired with primary
   failures and interrupts.
4. Run a multi-thousand-frame fake-clock soak with alternating geometry and a sink
   that retains no output history.

Exit condition: all shell behavior is deterministic and system-independent under
fakes, including every cleanup branch.

### P5.7 — Live WezTerm acceptance

Run production modules in disposable WezTerm panes, never through probe-only frame
or protocol implementations:

1. horizontal and vertical CJK at the default 30 FPS;
2. repeated pixel and cell resize transitions;
3. normal harness stop, real `Ctrl+C`, injected runtime failure, and repeated restore;
4. state inspection after each case: primary screen, visible cursor, synchronized
   mode off, and no owned image/placement;
5. a five-minute structured workload with frame count, latency, bytes, resize count,
   and WezTerm working-set delta recorded.

Live harnesses may inject a stop predicate or failing collaborator directly; do not
add production CLI flags for tests. Record the exact environment and commands in the
phase report.

Exit condition: the production adapter reproduces the Phase 0 lifecycle and
longevity evidence in the reference WezTerm environment.

### P5.8 — Documentation and phase report

1. Update `SPEC.md`, ADR 0001, architecture, and user-facing runtime prerequisites.
2. Document recovery for hard termination and broken output.
3. Record offline gates and live acceptance evidence in `docs/PHASE_5_REPORT.md`.
4. Update README to identify the remaining release-packaging boundary.

Exit condition: documentation describes implemented production behavior and its
physical cleanup limitations exactly.

## Planned file layout

```text
src/mojit/adapters/clock.py
src/mojit/adapters/wezterm/viewport.py
src/mojit/adapters/wezterm/png_encoder.py
src/mojit/adapters/wezterm/kitty_protocol.py
src/mojit/adapters/wezterm/terminal_state.py
src/mojit/adapters/wezterm/backend.py
src/mojit/cli.py

tests/unit/adapters/test_clock.py
tests/unit/adapters/wezterm/test_viewport.py
tests/unit/adapters/wezterm/test_png_encoder.py
tests/unit/adapters/wezterm/test_kitty_protocol.py
tests/unit/adapters/wezterm/test_terminal_state.py
tests/unit/adapters/wezterm/test_backend.py
tests/unit/test_cli.py
tests/integration/test_wezterm_pipeline.py
tests/integration/test_cli_runtime.py
tests/integration/test_shell_longevity.py
tests/live/wezterm_acceptance.py
```

The live acceptance file is not collected by the default offline test pattern. It is
run explicitly inside a disposable WezTerm environment.

## Required checks

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m pytest `
  --cov=mojit.adapters.wezterm --cov=mojit.adapters.clock --cov=mojit.cli `
  --cov-fail-under=95
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m ruff format --check src tests
.\.venv\Scripts\python.exe -m compileall -q src tests
```

Live reference gate:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\live\wezterm_acceptance.py -m wezterm_live
```

Offline tests never skip. The live gate is separate, explicit, and required to close
the phase on the recorded Windows/WezTerm reference environment.

## Phase gate

Phase 5 is complete only when:

- all request, font, output, pane, and geometry checks finish before mutation;
- viewport subprocess calls are exact, bounded, no-shell, and isolated from stdin;
- PNG encoding preserves exact RGBA and Kitty transmission is correctly chunked;
- one process-owned image and placement are replaced without accumulation;
- cell geometry affects placement while pixel geometry affects layout;
- synchronized update, cursor, alternate screen, and image cleanup follow the fixed
  state machine;
- cleanup is successful after normal completion, real interrupt, and injected
  failures, and repeated restore is harmless;
- cleanup failures cannot be mistaken for successful termination or erase the
  primary diagnostic;
- CLI run mode starts production animation, `Ctrl+C` exits according to the fixed
  policy, and list mode remains isolated;
- application and rendering layers remain free of WezTerm and shell dependencies;
- offline full tests, focused coverage, lint, format, compile, dependency, failure,
  and longevity gates pass;
- live disposable-pane lifecycle and five-minute acceptance gates pass;
- the hard-termination/broken-stream limitation is documented honestly;
- no release-packaging or cross-terminal scope leaks into the phase.

## Implementation increments

Keep commits independently reviewable:

1. shell contracts, PNG encoder, and pure Kitty protocol;
2. bounded viewport acquisition;
3. terminal state machine and concrete backend;
4. system clock and CLI runtime composition;
5. offline failure/longevity gates;
6. live acceptance evidence, documentation, and phase report.

## Follow-up boundary

After Phase 5, the functional v1 is complete from a source checkout. The next phase
is release engineering: pin and bundle an application-controlled FriBiDi runtime and
license notices, build installable artifacts, test a clean Windows image without
ambient DLLs, provision or explicitly supply the CJK font, and run installed-command
smoke acceptance.
