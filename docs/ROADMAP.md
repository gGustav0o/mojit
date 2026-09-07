# Post-v1 roadmap

Status: active roadmap.

Phases 0-6 delivered the v1 baseline and are complete. Their plans and reports are
historical records. New development starts here.

The roadmap intentionally sequences **product primitives before spectacle**. A new
effect is valuable only if it strengthens a reusable scene model rather than adding
another isolated special case.

## Phase 7 — Scene composition foundation

**Status:** complete (2026-09-06).

### Goal

Introduce the smallest scene/layer model that can express the existing v1 text
rendering path and can later compose text with independent ambient visuals.

### Required outcomes

- There is one clear pure composition boundary that turns explicit scene inputs into
  a `Frame` (names are illustrative, not prescribed).
- A scene can contain multiple ordered visual contributions/layers.
- Layers do not access terminal I/O, files, clocks, environment, or global RNG.
- Z-order/compositing and clipping behavior are explicit and deterministic.
- Existing v1 text/effect behavior remains available without forcing users to adopt a
  new scene syntax.
- Fixed viewport + time/frame index + seed + scene description can be tested
  deterministically.
- Existing resize/lifecycle/application guarantees are preserved.
- Architecture documentation is updated to describe the implemented model.

### Explicitly out of scope

- new terminal backends;
- native Kitty-terminal support;
- user-defined plugins;
- a GUI editor;
- a large preset library;
- speculative generic ECS/scene-graph infrastructure.

### Completion gate

Phase 7 is complete only when at least one test composes two independent layers into a
single deterministic frame, legacy behavior is covered, and the full practical
source verification suite passes.

### Completion evidence

- `core.scene` defines an immutable ordered `Scene`, the structural `Layer` contract,
  strict full-viewport validation, and deterministic back-to-front composition.
- `TextEffectLayer` adapts the existing text/effect contract, and `RenderSession`
  routes the unchanged v1 request through a one-layer scene.
- Pure tests cover two-layer ordering, repeatability, immutable outputs, invalid
  layer boundaries, resize-independent inputs, and byte-equivalent legacy output.
- The source gate passes with 568 tests and 96.93% coverage, plus lint, format,
  compile, and diff checks.

---

## Phase 8 — Procedural ambience primitives

**Status:** complete (2026-09-06).

### Goal

Prove that the scene model supports visual content that is not merely a transform of
one text mask.

### Required outcomes

Implement a small coherent set of reusable procedural layers. The initial reference
set should include at least three visually distinct primitives from this family:

- rain;
- stars;
- snow;
- drifting/sakura-like particles;
- subtle noise/glow/background motion.

The agent should choose the smallest set that best exercises different composition
and motion requirements; implementing every listed effect is not required.

Each primitive must:

- use explicit deterministic randomness when randomness is needed;
- remain bounded in memory over indefinite execution;
- resize without retaining stale viewport-sized history;
- expose a compact configuration model based on visual concepts;
- compose with the existing Japanese text layer(s).

### Completion gate

At least one reference composition must combine Japanese text with two independent
ambient layers and remain deterministic under tests.

### Completion evidence

- Frozen `RainLayer`, `StarsLayer`, and `SnowLayer` configurations provide three
  visually distinct procedural primitives over the Phase 7 layer contract.
- Every frame is regenerated from explicit viewport/time/seed inputs with a local
  RNG, no retained simulation history, and a hard 4,096-particle per-layer cap.
- Tests cover deterministic replay, motion, immutable full-viewport output, global
  RNG isolation, zero density, bounded counts, resize replay, and invalid visual
  configuration.
- A pure integration test composes Japanese text with independent stars and rain in
  one deterministic ordered scene.
- The full source gate passes with 612 tests and 97.14% coverage, plus lint, format,
  compile, and diff checks.

---

## Phase 9 — Scene configuration and presets

**Status:** complete (2026-09-06).

**Completion summary (2026-09-06):** built-in preset discovery and selection are implemented.
`--list-scenes` reports the stable `rainy-night`, `snowfall`, and `space` registry;
`--scene NAME` and the optional root TOML `scene` key select a preset with normal
CLI-over-file precedence. Unknown names fail before text/font/terminal work, and the
ordinary v1 text path remains the default. Strict custom configuration uses
`scene_version = 1` plus an ordered `layers` array of `stars`, `rain`, `snow`, and
exactly one `text` layer, capped at 16 total layers. It rejects unknown
versions/types/layers, oversized compositions, and ambiguity with a named preset
before external runtime work.

### Goal

Make the scene engine useful without Python code.

### Required outcomes

- Define a strict, versionable configuration representation for scenes/layers.
- Preserve the existing simple CLI and existing config behavior where practical.
- Add discovery/listing for built-in scenes or presets.
- Ship a small curated preset set that demonstrates genuinely different compositions,
  not parameter variations of the same scene.
- Reject invalid scene configuration before mutating terminal state.
- Keep configuration independent of incidental implementation class names.

Illustrative preset themes may include `rainy-night`, `space`, `snow`, or similar
Japanese/anime-adjacent ambience. Names and exact CLI syntax are product details to be
chosen during implementation and documented when frozen.

### Completion gate

A fresh user can select a built-in scene and can define a custom multi-layer scene in
configuration without changing source code.

---

## Phase 10 — Visual polish, longevity, and usability

**Status:** complete (2026-09-07).

### Completion evidence

- Transport-faithful references at 320×200, 930×1012, and 1400×500 exposed that
  one-pixel ambience disappeared during supported WezTerm cell sampling. Preset-scale
  rain width/length and star radius were tuned until `rainy-night`, `snowfall`, and
  `space` remained distinct after LANCZOS downsampling and color quantization. A
  semantic integration test now enforces that ambient cells survive this boundary.
- All presets rendered and restored cleanly in live WezTerm at both a 930×506
  landscape pane and a 330×1012 portrait pane. The structured soak changes both width
  and height and records the exact observed viewport sequence.
- Multi-layer 1,000-frame application and transport tests enforce bounded ownership.
  A five-minute `rainy-night` run presented 2,104 frames across four detected
  two-axis resizes, wrote 24,176,946 terminal bytes, and restored cleanly. Its observed
  WezTerm working-set delta was +44,834,816 bytes; this process-level sample is
  recorded as evidence, not treated as a general leak bound.
- Batch scene composition removed pairwise immutable frame copies. A second fused
  mask-colorization path preserves the established neon reference bytes while
  avoiding three intermediate RGBA frames. At 930×667 the warmed complete preset
  render improved from roughly 83–91 ms to 65–69 ms per frame. A final 30-second live
  run achieved 7.36 FPS against target 8 with 7.5% skipped opportunities (including
  four live resizes), 14.19 ms average presentation, and correct cleanup.
- Unknown/malformed scene configuration still fails before terminal creation, while
  injected runtime failure now exercises a multi-layer preset and restores the live
  terminal. Preset composition remains explicit readable layer configuration in
  `scenes.presets`, not runtime special cases.
- The final source gate passes with 665 tests and 97.20% coverage, plus lint, source
  formatting, compile, CLI smoke, and diff checks.

### Goal

Turn the technically working scene engine into something worth leaving on screen.

### Required outcomes

- Tune reference scenes based on actual WezTerm rendering, not screenshots/tests only.
- Verify resize behavior across representative pane sizes and aspect ratios.
- Verify long-running bounded-state behavior with multi-layer scenes.
- Measure practical presentation cost and remove obvious avoidable frame work.
- Ensure failures before terminal entry and cleanup after runtime failures remain
  correct under the expanded scene path.
- Keep presets readable/configurable rather than encoding magic behavior in the
  runtime.

Visual fidelity in live use is an acceptance criterion here. Historical v1 transport
acceptance is necessary evidence, not sufficient evidence that a scene looks good.

---

## Future — Backend expansion

This section is intentionally **not active work**.

After Phases 7-10 are mature, the project may evaluate a native Kitty-terminal
backend and richer image-oriented layers. At that point, use measured capabilities of
an actual second terminal backend to extract only the abstractions that are genuinely
shared.

Do not pre-build a universal terminal framework now.

---

## Roadmap maintenance rules

- Work on the highest-priority unblocked active/queued phase.
- Keep each implementation increment bounded and independently verifiable.
- If implementation evidence invalidates a roadmap assumption, update this document
  and record a durable architectural choice in a new ADR when appropriate.
- Do not edit completed Phase 0-6 plans/reports to make history match the new design.
- Do not promote Future work into the active roadmap without a concrete reason or
  explicit product decision.
