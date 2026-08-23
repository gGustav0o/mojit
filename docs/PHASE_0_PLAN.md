# Phase 0: technical-risk elimination

Status: architecture and runtime work completed on 2026-08-23; clean-image release
packaging remains an explicit downstream gate. See [Phase 0 report](PHASE_0_REPORT.md).

## Goal

Phase 0 must replace the assumptions with measured facts that determine the v1
architecture. It does not implement the product. The phase is complete only when a
minimal integrated probe can render Japanese text in WezTerm, survive resize and
failure, and each long-lived choice is captured in an ADR.

The four risks are:

1. reliable vertical Japanese shaping on the supported Windows installation;
2. reliable pixel viewport measurement, including when text arrives through stdin;
3. a graphics transport capable of repeated full-frame replacement without resource
   accumulation;
4. unconditional restoration of terminal state.

## Non-goals

Phase 0 does not contain the production CLI, configuration resolution, effect system,
font-size search, cache, final animation loop, or reusable cross-terminal abstraction.
A probe may use fixed text, a fixed font, fixed dimensions, and a synthetic frame.

## Working rules

- Record evidence before choosing an implementation.
- Change one independent variable per benchmark.
- Keep probe code under `spikes/`; do not import it from `src/mojit`.
- Record environment versions and hardware with every result.
- Use explicit timeouts for terminal queries; no probe may block indefinitely.
- Every terminal-mutating probe restores state from `finally` and supports repeated
  invocation in the same pane.
- Promote only the smallest proven mechanism into production in a later phase.

## Evidence format

Each result file under `spikes/results/` must contain:

```text
Question
Environment
Probe and exact command
Inputs and controlled variables
Raw measurements location
Observations
Failure modes
Conclusion
ADR impact
```

## Work sequence

### P0.0 — Reproducible baseline

Purpose: make every later result attributable to a known environment.

Actions:

1. Create a local Python 3.11+ environment and install the package dependencies.
2. Record Windows build, WezTerm version, Python version, Pillow feature report,
   NumPy version, CPU, display scaling, pane dimensions, and selected font file.
3. Select one horizontal and one vertical corpus:
   `電脳世界`, `警告、「猫」。`, and a string containing `ー` and brackets.
4. Record the font file checksum so typography results can be reproduced.

Artifacts:

- `spikes/results/000-environment.md`;
- a small environment-report command or script if manual collection is error-prone.

Exit condition: another developer can reproduce the same baseline without guessing
which terminal, font, or library build was used.

### P0.1 — Vertical typography capability

Purpose: decide how v1 guarantees `direction="ttb"` on Windows.

Probe: `spikes/typography/vertical_probe.py`.

Actions:

1. Record `PIL.features.check_feature("raqm")` and the linked feature versions.
2. Load the chosen CJK font and render the corpus horizontally and with
   `direction="ttb", language="ja"`.
3. Compare `textbbox` with non-transparent output bounds.
4. Inspect punctuation, prolonged sound mark, brackets, clipping, and anchors.
5. Repeat with a missing/invalid font and without the required Raqm dependency.
6. Record installation or packaging steps required for FriBiDi on a clean machine.

Measurements:

- feature availability;
- bounding boxes and output dimensions;
- rasterization time for several font sizes;
- deterministic image hashes;
- annotated output PNGs for visual review.

Exit conditions:

- vertical output is visually acceptable for the fixed corpus;
- missing capabilities fail before animation starts with a precise diagnosis;
- the distribution strategy for Raqm/FriBiDi and the default font is known.

Decision records:

- `0003-vertical-shaping-distribution.md`;
- `0004-default-cjk-font.md`.

### P0.2 — Pixel viewport and input-channel isolation

Purpose: obtain stable pane dimensions without breaking stdin text input.

Probe: `spikes/wezterm/viewport_probe.py`.

Candidate mechanisms must be tested, not assumed: terminal window/cell-size queries,
Win32/ConPTY information, and a narrowly scoped WezTerm-specific mechanism.

Scenarios:

1. normal interactive invocation;
2. positional text;
3. PowerShell piped stdin;
4. repeated grow and shrink operations;
5. split pane, zoomed pane, display scaling, and focus changes;
6. missing response and malformed response.

Measurements:

- reported cell and pixel dimensions;
- query latency and timeout frequency;
- stability over at least 20 resize transitions;
- whether terminal replies remain available when `sys.stdin` is a pipe.

Exit conditions:

- the chosen mechanism returns the current drawable pixel size after resize;
- it has a bounded timeout and a clear failure path;
- piped text and terminal replies cannot consume one another;
- its polling cost is low enough for the planned runtime strategy.

Decision record: `0002-pixel-viewport-measurement.md`.

### P0.3 — Graphics transport benchmark

Purpose: choose exactly one v1 protocol and its frame-replacement lifecycle.

Probe: `spikes/wezterm/transport_probe.py`.

Compare only viable direct transports supported by WezTerm:

- Kitty graphics with chunked direct data;
- iTerm2 inline image protocol as a simplicity baseline.

For Kitty, separately measure PNG and zlib-compressed RGBA. Reuse deterministic
image/placement identifiers and explicitly delete or replace terminal resources.
Do not benchmark `wezterm imgcat` subprocess creation as a per-frame architecture.

Test matrix:

- 1280×720 and 1920×1080 frames;
- opaque and alpha-heavy frames;
- static, low-change, and high-change synthetic animation;
- target rates 15, 30, and 60 FPS;
- at least 30 seconds per measured case after warm-up.

Measurements:

- encode/compress time per frame, median and p95;
- bytes written per frame and per second;
- achieved presentation rate;
- Python process memory before and after the run;
- visible flicker, stale placements, cursor movement, and terminal responsiveness;
- cleanup after normal completion and interruption.

Decision rule:

Choose the simplest mechanism that can sustain the selected default FPS at the
reference viewport without unbounded resource growth. Treat 60 FPS as a measured
capability, not an architectural assumption. If no transport meets the target, the
result must drive an explicit FPS or frame-size change in the specification.

Decision record: `0001-terminal-graphics-protocol.md`.

### P0.4 — Terminal lifecycle and failure matrix

Purpose: prove that terminal cleanup is unconditional and idempotent.

Probe: `spikes/wezterm/lifecycle_probe.py`.

Exercise:

- normal exit;
- `Ctrl+C` during query, encoding, write, and wait;
- deliberate exception after each state mutation;
- broken output pipe;
- two consecutive runs in the same pane;
- resize during frame transmission.

Verify after every case:

- primary screen is restored;
- cursor is visible;
- synchronized-rendering mode is not left active;
- images and placements owned by the process are removed;
- `restore()` can be called more than once safely.

Exit condition: all cases pass, or each unavoidable terminal limitation is captured
as a documented constraint with an actionable recovery instruction.

### P0.5 — Minimal integrated proof

Purpose: validate the intersection of the decisions rather than each mechanism alone.

The proof must:

1. accept fixed positional text and piped text;
2. rasterize one horizontal or vertical CJK mask using the selected font setup;
3. present a simple deterministic pulse for at least five minutes;
4. adapt to repeated resize;
5. exit and restore cleanly on `Ctrl+C` and an injected exception.

This is still spike code. It must not introduce the production configuration model,
effect registry, cache, or general backend interface.

Exit condition: the integrated proof runs on the recorded reference environment and
its observations are consistent with P0.1–P0.4.

### P0.6 — Decision and phase gate

Actions:

1. Write and accept ADRs 0001–0004.
2. Add any measured constraints or clarified defaults back to `SPEC.md`.
3. Decide the default FPS and whether 60 FPS is guaranteed or best-effort.
4. Confirm the `TextMask` coordinate invariant for the production model.
5. Convert every unresolved observation into a named follow-up or an explicit
   non-goal; leave no implicit assumption.
6. Review the intended production package boundaries before promoting any code.

Phase 0 is complete when:

- all four ADRs are accepted;
- the integrated proof passes;
- terminal restoration passes the failure matrix;
- vertical shaping and default-font distribution are reproducible on clean Windows;
- viewport measurement works with positional and piped input;
- the chosen transport has recorded performance and resource-use evidence;
- `SPEC.md` contains every user-visible constraint revealed by the experiments.

## Optimal execution order

```text
P0.0 baseline
   ├── P0.1 typography ─────────────┐
   └── P0.2 viewport ─► P0.3 transport
                                   ├── P0.4 lifecycle
                                   └── P0.5 integrated proof
                                              ↓
                                      P0.6 phase gate
```

P0.1 is independent of terminal work and can proceed in parallel. P0.3 should not
lock placement/scaling behavior until P0.2 establishes viewport semantics. Lifecycle
testing follows the selected transport, and the integrated proof starts only after
the independent risks have bounded outcomes.

Suggested timeboxes are half a day for P0.0, one day for P0.1, one to two days for
P0.2–P0.4, and half a day for integration and ADR review. A timebox may end with a
negative result, but never with an undocumented assumption.
