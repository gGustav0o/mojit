# Phase 1: deterministic typography core

## Goal

Implement and prove the pure domain foundation that transforms validated text,
font data, orientation, viewport, and margin into a deterministic full-viewport
`TextMask`.

Phase 1 ends before effects, terminal integration, and the production animation
loop. Its output must be usable without WezTerm, stdin, filesystem access, config
files, or a wall clock.

## Scope

Phase 1 includes:

- immutable core models and ndarray invariants;
- deterministic random-state derivation;
- pixel-space layout primitives;
- logarithmic maximum-font-size search;
- Pillow/Raqm measurement and mask rasterization from in-memory font data;
- immutable typography request/cache identity;
- unit tests and a narrowly scoped real-font integration test.

## Non-goals

Do not implement in this phase:

- CLI parsing, stdin, TOML, or configuration precedence;
- mutable mask caching;
- effects or compositor operations beyond model validation;
- frame scheduling or animation orchestration;
- WezTerm viewport, Kitty transport, or terminal lifecycle code;
- FriBiDi release packaging;
- general Windows font discovery;
- cross-terminal or pluggable typography abstractions.

## Fixed design decisions

### Dependency boundary

```text
adapters.font_resource ──reads──► font file
          │
          └──produces──► bytes + stable fingerprint
                              │
                              ▼
                       core.typography
                              │
                              ▼
                    full-viewport TextMask
```

`core` never receives a path and never performs filesystem I/O. The adapter reads
the file and derives a stable content fingerprint. Pillow may construct font faces
from the in-memory bytes inside `core.typography`.

### Array ownership

`TextMask` and `Frame` own C-contiguous copies of their arrays. Construction validates
shape and `uint8` dtype, then marks the stored arrays read-only. A frozen dataclass
alone is insufficient because it does not make NumPy buffers immutable.

### Geometry

- viewport dimensions are positive integers;
- `0 <= margin < 0.5`;
- reserved pixels per edge are `ceil(dimension * margin)`;
- glyph ink bounds, including negative Pillow bearings, determine fit and centering;
- centering uses a documented integer rounding rule and must never clip fitted ink;
- `TextMask` origin is always `(0, 0)` and its shape equals the viewport.

### Typography

- horizontal mode uses Raqm-compatible Japanese shaping;
- vertical mode uses `direction="ttb"`, `language="ja"`;
- font size is an integer of at least 1 pixel;
- maximum size is found by exponential bound discovery followed by binary search;
- blank text, missing glyph ink, unsupported vertical shaping, invalid font data, and
  an impossibly small viewport produce explicit domain-facing errors;
- v1 has no manual per-character vertical fallback.

### Determinism

Random state is derived from canonical bytes containing:

```text
seed
effect identifier
frame index
```

Use a stable cryptographic digest and an explicitly selected NumPy bit generator.
Never use Python's process-randomized `hash()` or global NumPy/Python RNG state.

### Cache identity

The immutable typography key contains every value that can change the mask:

```text
text
font content fingerprint
orientation
viewport width and height
margin
language
direction and shaping options
```

It contains no mutable font object or ndarray. The application-owned mutable cache
is deferred until orchestration needs it.

## Work sequence

### P1.0 — Contract tests first

Define executable tests for the public invariants before implementation:

1. valid and invalid model construction;
2. ndarray shape, dtype, ownership, contiguity, and read-only state;
3. full-viewport mask coordinates;
4. deterministic equality and cache-key behavior;
5. forbidden dependency checks for `core`.

Artifacts:

- `tests/unit/core/test_models.py`;
- `tests/unit/core/test_dependencies.py`.

Exit condition: tests express all model boundaries and initially fail only because
the production behavior is absent.

### P1.1 — Core value objects

Implement in `src/mojit/core/models.py`:

- `Orientation`;
- `Viewport`;
- `TextMask`;
- `Frame`;
- `RenderContext`;
- narrow validation exceptions where callers can act differently.

Rules:

- use frozen, slotted dataclasses where they improve the value semantics;
- reject booleans where an integer is required;
- reject non-finite or negative elapsed time;
- do not place configuration defaults in core models;
- do not expose mutable array aliases.

Exit condition: model tests pass independently of Pillow and WezTerm.

### P1.2 — Deterministic randomness

Implement `src/mojit/core/randomness.py`:

1. canonical encoding for seed, effect ID, and frame index;
2. stable digest-to-seed derivation;
3. construction of a fresh local NumPy generator;
4. no mutation of global random state.

Tests must prove:

- identical inputs produce identical sequences across separate generator instances;
- changing any input changes the derived stream;
- Unicode effect identifiers are encoded unambiguously;
- global `random` and `numpy.random` state are untouched;
- invalid frame indices fail explicitly.

Exit condition: stochastic effects can later depend on one stable function only.

### P1.3 — Pure pixel layout

Implement `src/mojit/core/layout.py` without Pillow imports:

- available bounds after margin reservation;
- normalized ink dimensions from a bounding box;
- fit predicate;
- centered integer placement corrected for negative bearings;
- maximum-font-size search using a supplied measurement callable.

Tests cover odd/even viewport dimensions, zero and negative bearings, extreme valid
margins, single-pixel fit, no-fit behavior, horizontal and vertical aspect ratios,
and proof that measurement-call growth is logarithmic rather than linear.

Exit condition: layout policy is fully testable with synthetic metrics.

### P1.4 — Font resource boundary

Implement `src/mojit/adapters/font_resource.py` as the only Phase 1 filesystem shell:

1. resolve an explicit path supplied by the caller;
2. read bytes once;
3. compute SHA-256 content identity;
4. reject missing, non-file, unreadable, empty, and invalid font resources;
5. return an immutable value containing bytes and fingerprint.

Do not perform default-font selection or general discovery here; those policies
belong to later config/application work.

Exit condition: core typography can operate without paths or open file handles.

### P1.5 — Typography measurement and rasterization

Implement `src/mojit/core/typography.py`:

1. validate text and shaping mode;
2. construct Pillow font faces from supplied bytes;
3. measure with the exact options later used for drawing;
4. find the maximum fitting font size through `core.layout`;
5. center by ink bounds;
6. draw directly into a viewport-sized grayscale image;
7. convert once to an owned, read-only `uint8` NumPy array;
8. return `TextMask` plus only the layout metadata actually required by callers.

Horizontal and vertical code paths share sizing, centering, validation, and output
construction. Orientation-specific Pillow options remain localized.

Tests use:

- synthetic measurement tests for layout policy;
- malformed font bytes for error mapping;
- the recorded reference font for an environment-gated integration test;
- the Phase 0 punctuation corpus for horizontal and vertical snapshots/hashes.

Exit condition: both orientations produce deterministic, unclipped, full-viewport
masks on the reference environment.

### P1.6 — Typography identity

Add the immutable mask identity next to the typography request model. Tests prove
that every mask-affecting input changes equality/hash and irrelevant runtime values
such as frame index and elapsed time cannot enter the key.

Do not implement eviction, capacity policy, or mutable storage in this phase.

Exit condition: later application caching cannot silently reuse an incompatible mask.

### P1.7 — Integrated core gate

Run one non-terminal integration path for each orientation:

```text
font file
  ↓ adapter read + fingerprint
font bytes + typography request
  ↓ layout + Pillow/Raqm
TextMask
  ↓ invariant and deterministic hash checks
verified mask
```

Verify:

- `電脳世界` horizontal;
- `警告、「猫」。` vertical;
- resize to at least three viewport aspect ratios;
- repeated requests produce identical hashes;
- smaller and larger viewports select appropriate font sizes;
- no test imports `spikes` into production code.

## Test strategy

Fast default suite:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m ruff format --check src tests
```

Reference-environment suite:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\integration -m typography_reference
```

System-dependent tests must skip with a precise reason when the recorded font or
Raqm/FriBiDi capability is absent. Unit tests must never skip.

## Implementation increments

Keep each increment independently reviewable:

1. model contracts and models;
2. deterministic randomness;
3. layout primitives and binary search;
4. font-resource boundary;
5. horizontal typography;
6. vertical typography;
7. cache identity and integrated gate.

Do not begin the next increment while the current one has failing tests or lint.

## Phase gate

Phase 1 is complete only when:

- all core models enforce their documented invariants;
- stored arrays cannot be mutated through caller-owned aliases;
- layout selects the largest fitting font size without linear search;
- horizontal and vertical masks are centered, unclipped, full-viewport, and
  deterministic on the reference environment;
- typography core performs no filesystem, terminal, config, clock, or global-RNG I/O;
- the font adapter is the only filesystem boundary introduced by the phase;
- the cache identity covers every mask-affecting input;
- unit, reference integration, lint, formatting, and dependency-boundary checks pass;
- no Phase 2+ behavior has leaked into the implementation.

## Follow-up boundary

After this gate, Phase 2 should implement config/input resolution and the production
CLI boundary. Effects, compositor, runtime caching, scheduling, and the WezTerm
backend remain later phases.
