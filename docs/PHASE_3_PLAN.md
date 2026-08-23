# Phase 3: pure compositor and deterministic effects

Status: complete. The verified outcome is recorded in
[PHASE_3_REPORT.md](PHASE_3_REPORT.md).

## Goal

Transform a validated full-viewport `TextMask`, deterministic `RenderContext`, and
effect seed into an immutable full-viewport `Frame` through reusable pure compositor
operations and an explicit immutable v1 effect registry.

Phase 3 ends at an in-memory `Frame`. It does not load fonts, query or mutate the
terminal, schedule frames, cache masks, or encode PNG.

## Scope

Phase 3 includes:

- strict full-viewport compositor primitives;
- the minimal immutable effect API;
- `neon`, `pulse`, `chromatic`, and deterministic `glitch` renderers;
- immutable effect registration and lookup;
- validation of configured effect identifiers against the registry;
- functional `--list-effects` output without unrelated I/O;
- deterministic, visual-reference, dependency, and integration tests;
- SPEC and architecture updates for the final rendering contracts.

## Non-goals

Do not implement in this phase:

- `TextMask` caching;
- animation loop, frame scheduler, resize handling, or clocks;
- WezTerm viewport queries, terminal state, Kitty protocol, or PNG encoding;
- effect-specific CLI/TOML parameters;
- effect composition or user-defined effects;
- plugin discovery, dynamic imports, inheritance hierarchies, factories, or DI;
- GPU/shader paths, color management, or gamma-correct compositing;
- new third-party dependencies.

## Fixed architecture

```text
core.models
  ▲
  ├── core.compositor
  └── core.randomness
          ▲
          │
effects.api ◄── effects implementations ◄── effects.registry
                                              ▲
                                              │
                                     cli composition root
```

Rules:

- `core.compositor` depends only on core models, Pillow, NumPy, and stdlib;
- effects depend only on `core` and `effects.api`;
- registry imports concrete effects, but concrete effects never import registry;
- no effect imports application, config, adapters, CLI, filesystem, terminal, clock,
  `random`, or global `numpy.random` APIs;
- application and CLI continue passing effect identifiers, not renderer instances,
  into `PreparedRun`;
- all public effect and compositor outputs are `TextMask` or `Frame`, preserving the
  immutable array contracts established in Phase 1.

## Pixel and compositing contract

Freeze these rules before implementation:

```text
alpha/color storage:  straight-alpha uint8 sRGB bytes
canvas:               full viewport for every TextMask and Frame
outside transforms:   transparent black
translation:          integer pixels, clipped, never wrapped
scale origin:         viewport center
scale sampling:       Pillow LANCZOS
blur:                 Pillow GaussianBlur
composition:          standard source-over
transparent pixels:   RGB = 0 when alpha = 0
input mutation:       forbidden
```

No operation silently changes dtype, canvas dimensions, or coordinate system.
Invalid shapes, non-finite values, booleans passed as numbers, mismatched viewports,
negative blur radii, and non-positive scale factors fail explicitly.

Implement in `src/mojit/core/compositor.py` only the reusable operations required by
the v1 effects:

```text
translate_mask(mask, dx_px, dy_px) -> TextMask
scale_mask_centered(mask, factor) -> TextMask
blur_mask(mask, radius_px) -> TextMask
colorize_mask(mask, rgba_color) -> Frame
alpha_composite(bottom, top) -> Frame
merge_color_channels(red, green, blue) -> Frame
warp_horizontal_bands(mask, shifts) -> TextMask
```

`warp_horizontal_bands` owns the shared crop/shift/paste logic used by glitch. It
uses immutable validated band descriptors and zero-fill clipping. Do not expose a
generic affine/scene-graph API merely to mirror the conceptual operation list in the
SPEC.

Pillow supplies resize, blur, and source-over behavior. NumPy supplies exact channel
assembly and clipped integer translations. Effects must not reimplement these
operations locally.

## Effect API

Add `src/mojit/effects/api.py`:

```python
@dataclass(frozen=True, slots=True)
class EffectConfig:
    seed: int

Effect = Callable[[TextMask, RenderContext, EffectConfig], Frame]
```

`EffectConfig` contains only the current cross-effect runtime option. Visual tuning
constants stay private to each concrete effect until a user-facing option actually
exists.

Every renderer must:

1. validate that mask dimensions equal `context.viewport`;
2. return one full-viewport immutable `Frame`;
3. leave the mask and context untouched;
4. depend only on explicit arguments;
5. derive animation from `elapsed_seconds` and stochastic variation from
   `seed + fixed effect ID + frame_index`;
6. keep transparent output outside the composition.

Do not introduce a base class. The type alias and four functions are sufficient.

## Effect contracts

### Neon

- cyan/blue outer glow from two shared Gaussian-blur layers;
- high-opacity pale core from the original mask;
- slow bounded glow breathing derived from `elapsed_seconds`;
- blur radii derived from the shorter viewport side and clamped to positive pixel
  ranges;
- no randomness.

### Pulse

- centered periodic scale in a range that does not exceed the fitted source bounds;
- smooth sinusoidal phase derived only from `elapsed_seconds`;
- one stable color treatment and optional shared low-radius glow;
- no randomness and no accumulated transform state.

### Chromatic

- separately translated red, green, and blue alpha channels;
- bounded oscillating pixel offset derived from viewport size and
  `elapsed_seconds`;
- channel merge performed once by the compositor;
- no randomness and no duplicated alpha-compositing code.

### Glitch

- deterministic horizontal band displacement with zero-fill clipping;
- a bounded number of bands and offsets proportional to viewport dimensions;
- optional deterministic channel separation assembled from shared primitives;
- one fresh generator from `make_rng(seed, "glitch", frame_index)` per frame;
- no global RNG, mutable history, or previous-frame dependency.

The first implementation increment must render a fixed Japanese reference mask at
representative frames, tune private constants once, and record them. Subsequent
changes to those constants are treated as visible behavior changes.

## Registry and CLI boundary

Implement `src/mojit/effects/registry.py` with:

```text
EFFECTS: immutable Mapping[str, Effect]
effect_names() -> tuple[str, ...]
get_effect(effect_id) -> Effect
UnknownEffectError
```

Registry rules:

- exact v1 identifiers: `neon`, `glitch`, `chromatic`, `pulse`;
- names returned in stable alphabetical order;
- lookup has no fallback to the default effect;
- unknown but syntactically valid identifiers fail before font loading or terminal
  access;
- no decorator-driven registration or import-time mutation.

Complete the deferred CLI behavior:

```text
mojit --list-effects
```

It prints one identifier per line to stdout, returns `0`, writes nothing to stderr,
and does not read config/stdin/font, invoke shaping, or touch WezTerm. Normal run
preflight validates `PreparedRun.effect_id` through registry lookup but continues to
store only the identifier.

## Determinism contract

For equal `TextMask`, `RenderContext`, and `EffectConfig`, output bytes must be equal.

Tests independently prove:

- repeated calls yield identical `Frame.rgba`;
- caller-owned and model-owned inputs remain unchanged;
- changing `frame_index` changes `glitch` output;
- changing `seed` changes `glitch` output;
- effect execution does not alter Python or NumPy global RNG state;
- deterministic effects do not consult seed accidentally;
- no renderer reads wall-clock time or environment state.

`elapsed_seconds` is accepted as the deterministic value already present in
`RenderContext`. Enforcing `elapsed_seconds = frame_index / fps` remains the later
scheduler's responsibility because effects do not receive FPS.

## Work sequence

### P3.0 — Freeze visible raster rules

1. Add the pixel, alpha, clipping, resampling, and registry behavior above to
   `SPEC.md`.
2. Build a small deterministic reference-mask fixture independent of installed
   fonts.
3. Define representative contexts for frame `0`, a mid-cycle frame, and a later
   stochastic frame.
4. Confirm that effects use transparent output rather than inventing a background
   option.

Exit condition: implementation cannot choose blending or edge behavior implicitly.

### P3.1 — Compositor validation and exact transforms

1. Implement strict numeric, color, shape, and viewport validation.
2. Implement clipped translation and centered scaling.
3. Implement Gaussian blur and colorization.
4. Implement source-over frame composition and RGB channel merge.
5. Implement validated horizontal-band warp with shared crop/paste logic.
6. Prove no primitive mutates or shares writable storage with its input.

Exit condition: concrete effects need no image-manipulation code outside compositor
calls and simple parameter calculation.

### P3.2 — Effect contract and registry skeleton

1. Implement frozen `EffectConfig` and the callable alias.
2. Add one common mask/context viewport guard.
3. Define `UnknownEffectError`, immutable registry, stable name listing, and lookup.
4. Add dependency tests for core/effect/registry directions and forbidden I/O/RNG
   imports.

Exit condition: every supported effect has one explicit callable slot and registry
state cannot be mutated.

### P3.3 — Neon and pulse

1. Implement both effects entirely from compositor primitives.
2. Keep animation phase bounded and derived from `elapsed_seconds`.
3. Test phase endpoints, full-viewport output, transparent exterior, and repeated
   determinism.
4. Inspect the reference frames before freezing visual constants.

Exit condition: both continuous effects are deterministic and visually distinct.

### P3.4 — Chromatic and glitch

1. Implement chromatic channel displacement through shared translation/channel
   merge operations.
2. Implement glitch band generation with the Phase 1 local RNG.
3. Prove seed/frame sensitivity, clipping, bounded bands, and absence of global RNG
   changes.
4. Inspect horizontal and vertical Japanese reference masks for clipping artifacts.

Exit condition: stochastic behavior is reproducible and no effect owns mutable state.

### P3.5 — Registry-aware CLI

1. Validate selected effect IDs against the registry before font loading.
2. Map `UnknownEffectError` to the existing user-error exit code `2`.
3. Implement successful, stable `--list-effects` output.
4. Prove list mode performs no config, stdin, font, shaping, terminal, or subprocess
   work.

Exit condition: CLI and config cannot pass an unknown renderer into later runtime.

### P3.6 — Integrated pure-render gate

Exercise all four registry effects over:

1. sparse and dense synthetic masks;
2. odd and even viewport dimensions;
3. empty-alpha masks and masks touching viewport edges;
4. multiple frame indices and elapsed values;
5. minimum and maximum signed 64-bit seeds;
6. horizontal and vertical real-font reference masks where available.

For every case assert dimensions, dtype, immutable storage, deterministic bytes,
input preservation, and absence of terminal/subprocess activity.

Exit condition: `PreparedRun.effect_id -> registry -> Frame` works fully in memory.

### P3.7 — Documentation and phase report

1. Update `SPEC.md` and `docs/ARCHITECTURE.md` with implemented contracts only.
2. Record effect reference inputs, environment, and frame checksums.
3. Record test, coverage, lint, format, dependency, and reference-gate results in
   `docs/PHASE_3_REPORT.md`.
4. Update README to point to the completed phase and next boundary.

Exit condition: documentation matches code and tests without aspirational claims.

## Planned file layout

```text
src/mojit/core/compositor.py
src/mojit/effects/api.py
src/mojit/effects/registry.py
src/mojit/effects/neon.py
src/mojit/effects/pulse.py
src/mojit/effects/chromatic.py
src/mojit/effects/glitch.py

tests/unit/core/test_compositor.py
tests/unit/effects/test_api.py
tests/unit/effects/test_registry.py
tests/unit/effects/test_neon.py
tests/unit/effects/test_pulse.py
tests/unit/effects/test_chromatic.py
tests/unit/effects/test_glitch.py
tests/integration/test_effect_pipeline.py
tests/integration/test_effects_reference.py
```

Do not move compositor functions into effect modules or add application runtime code
to make integration tests pass.

## Required checks

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m pytest --cov=mojit.core.compositor `
  --cov=mojit.effects --cov-fail-under=95
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m ruff format --check src tests
.\.venv\Scripts\python.exe -m compileall -q src tests
```

System-independent unit and synthetic integration tests never skip. Real-font visual
references may skip only with a precise missing-font or missing-Raqm reason.

## Phase gate

Phase 3 is complete only when:

- all seven compositor operations obey the fixed full-viewport contracts;
- every effect is a pure callable returning an immutable `Frame`;
- all four v1 identifiers resolve through an immutable registry;
- unknown effects fail before font or terminal work;
- `--list-effects` succeeds with stable output and no unrelated I/O;
- deterministic output, glitch seed/frame sensitivity, and global RNG isolation are
  proven;
- effects contain no duplicated transforms, filesystem, terminal, clock, or mutable
  global state;
- synthetic and real-font reference gates pass;
- full tests, focused coverage, lint, format, compile, dependency, and documentation
  checks pass;
- no cache, scheduler, animation loop, or terminal behavior leaks into the phase.

## Implementation increments

Keep commits independently reviewable:

1. SPEC raster rules and compositor primitives;
2. effect API and immutable registry;
3. neon and pulse;
4. chromatic and glitch;
5. registry-aware CLI and `--list-effects`;
6. integrated references, architecture documentation, and report.

## Follow-up boundary

After this gate, the next phase may compose typography, mask caching, effects, and
frame scheduling in the application layer. Resize polling, terminal state, Kitty PNG
transport, and long-running cleanup remain outside Phase 3.
