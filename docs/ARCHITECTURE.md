# Architecture boundaries

Status: current boundaries through Phase 11 plus constraints for post-v1 evolution.

The detailed sections below describe the implemented v1 architecture and remain
constraints unless deliberately superseded. Product direction is defined in
[PRODUCT.md](PRODUCT.md) and sequencing in [ROADMAP.md](ROADMAP.md).

## Scene-engine evolution direction

Phase 7 introduced scene composition without changing terminal transport. The current
data flow is:

```text
Input / Config
    ↓
Scene description
    ↓
Scene / ordered layers
    ↓
Pure composition
    ↓
Frame
    ↓
Application scheduling
    ↓
Terminal backend
```

This remains an incremental direction, not a frozen class diagram. Introduce only the
types required by the active roadmap increment. In particular:

- existing text typography and effects should become reusable scene building blocks
  rather than be discarded;
- independent visual layers must compose before terminal presentation and must not
  know about WezTerm, subprocesses, clocks, files, or terminal state;
- deterministic inputs (scene/config, viewport, frame/time, seed) should reproduce
  deterministic frame output;
- scene composition must not require an ECS, plugin system, generic scene graph, or
  dependency-injection framework;
- the application remains responsible for time, resize observation, bounded caches,
  and presentation cadence;
- terminal transport remains an adapter boundary; Windows + WezTerm remains the
  concrete primary backend during the active roadmap;
- do not extract a generic cross-terminal hierarchy in anticipation of Kitty. A
  native Kitty-terminal backend should be designed only when it becomes active work
  and can provide real second-backend evidence.

Important terminology: the existing WezTerm backend can use the **Kitty Graphics
Protocol** as a wire protocol. That does not make the Kitty terminal application a
supported backend and does not authorize Kitty-specific development in the current
roadmap.

## Implemented v1 boundaries

`mojit` is a small modular monolith built around Functional Core / Imperative Shell.
The physical layout is intended to enforce these dependency directions:

```text
config.models ────────────────► core.models
config.resolve ───────────────► config.models
core ─────────────────────────► no project layer
effects ──────────────────────► core
layers ───────────────────────► core
scenes ───────────────────────► core + effects + layers
application ──────────────────► core + effects + scenes
adapters ─────────────────────► core models
cli (composition root) ───────► application + adapters + config
bootstrap ────────────────────► native runtime, then cli
```

Forbidden dependencies:

- `core` and `effects` must not import `application`, `adapters`, or `cli`;
- `core` must not accept `ResolvedConfig`; application maps it to narrow core options;
- effects must not access terminal state, files, clocks, or global random state;
- procedural layers must not access terminal state, files, clocks, environment, or
  global random state;
- typography must not own mutable caches;
- the WezTerm adapter must not contain layout or effect policy;
- experimental `spikes` code must not be imported by `src/mojit`.

The production `TextMask` is a full-viewport alpha plane. Its origin is fixed at
`(0, 0)`; typography owns glyph placement within that plane.

Core arrays are isolated C-contiguous `uint8` buffers backed by immutable bytes.
Callers cannot mutate a `TextMask` or `Frame` through the source ndarray or by
re-enabling the stored array's write flag. Construction copies mutable or uncertain
caller storage, while provably immutable bytes-backed arrays can transfer ownership
without a redundant full-plane copy.

The font adapter is the filesystem boundary: it returns immutable bytes and a SHA-256
content identity. Typography receives no path or open file handle. `TypographyKey`
is both the rendering request and cache identity; it contains only values that can
change the mask.

Horizontal auto-layout has three isolated boundaries. The BudouX adapter loads its
pinned Japanese model once per horizontal invocation and returns an immutable,
lossless phrase partition. Pure `text_layout.py` intersects those phrase boundaries
with Unicode-cluster and Japanese punctuation safety, balances a bounded candidate
set, and rejects automatic layouts containing an orphan line narrower than two
fullwidth cells. It knows nothing about BudouX, Pillow, fonts, viewports, or terminal
cells. `typography.py` measures the approved candidates with the selected font and
chooses the largest fitted size, using the original one-line form as the tie winner.
Vertical shaping bypasses language segmentation and remains one Raqm `direction="ttb"`
run. Phrases are derived from the text under a pinned model and bound to the
per-invocation rasterizer, so `TypographyKey` remains the complete cache identity and
no mutable layout state is introduced.

The config-file adapter owns discovery, bounded reads, and UTF-8 decoding. The TOML
module is pure and accepts only a closed set of root-level keys. Config resolution is
an explicit field-by-field `CLI > file > defaults` operation with source-relative font
paths.

The CLI is the Phase 2 composition root. Before terminal access it resolves one-line
Unicode input, loads and validates the font, checks Raqm/FriBiDi, creates an immutable
`PreparedRun`, and binds language phrases to the concrete rasterizer. Segmentation
failures therefore cannot leave terminal state mutated. The request itself contains
values and font bytes only: no paths, streams, parsed TOML, CLI namespaces,
environment, adapter objects, or parsed language models.

The compositor is a pure full-viewport boundary. Transform operations accept
immutable `TextMask`/`Frame` values, use clipped transparent edges, and return new
immutable values. Pillow owns LANCZOS resize, Gaussian blur, and source-over alpha;
NumPy owns clipped translation, band displacement, and channel assembly. Effects do
not duplicate these operations.

Phase 7 adds `core.scene` as the pure composition boundary. An immutable non-empty
`Scene` stores structural `Layer` values in explicit back-to-front order. Every layer
receives the same validated `RenderContext` and must return an immutable full-viewport
`Frame`; the boundary rejects non-frame and mismatched-viewport results before
presentation. The first contribution is retained unchanged for a one-layer scene.
Multi-layer scenes stream validated layer frames into one in-place Pillow source-over
pass and create one immutable result directly from Pillow's immutable output bytes.
Previously all layer frames remained live until composition completed; the streaming
fold now bounds simultaneous contribution
ownership independently of configured layer count. This makes z-order and viewport
clipping explicit without a retained scene graph, ECS, plugin API, or backend
knowledge.

A companion batch primitive colorizes and composites multiple masks directly. Neon
uses it for outer glow, inner glow, and glyph core, preserving the established bytes
without materializing three intermediate immutable RGBA frames.

`TextEffectLayer` adapts the existing text mask/effect/config triple to this structural
contract. `RenderSession` still owns the one-entry typography cache and deterministic
context construction, but now renders the v1 request as a one-layer `Scene`. The
single-layer result is byte-equivalent to the direct v1 effect output. Future
procedural layers may capture their own immutable visual configuration and seed, but
must continue to derive each frame solely from that configuration and the explicit
render context.

Phase 8 implements `layers` as a sibling of `effects` that depends only on the core
and side-effect-free third-party drawing/math libraries. `RainLayer`, `StarsLayer`,
and `SnowLayer` are frozen visual configurations. They rebuild a local particle field
for each frame from a signed 64-bit seed, stable layer identifier, current viewport,
and explicit elapsed time. They retain no simulation or viewport history, use no
global RNG, and cap each generated field at 4,096 particles. Density is
viewport-relative below that cap. Resize therefore replaces transient frame data
rather than migrating state, and rendering an earlier viewport/time again reproduces
the same frame. Periodic motion reduces elapsed time before multiplying by velocity or
frequency, so every finite non-negative `RenderContext.elapsed_seconds` remains a
valid deterministic input rather than overflowing intermediate motion arithmetic.

Phase 9 currently adds a small explicit built-in scene registry as a composition
layer above core/effects/procedural layers. `rainy-night`, `snowfall`, and `space`
are stable user-facing names mapped to ordinary `Scene` construction functions;
there is no discovery plugin mechanism. Preset-specific sub-seeds are derived from
the resolved run seed and stable layer names. The CLI validates a selected name
before text, font, shaping, or terminal work, while `RenderSession` remains the owner
of the viewport-specific text layer. CLI selection overrides the optional root TOML
`scene` key. The legacy absence of a scene continues to build exactly one text layer.

Custom scene TOML is a strict versioned product representation rather than a dump of
implementation objects. Version 1 accepts an ordered `layers` array containing
`stars`, `rain`, `snow`, and exactly one `text` entry, with at most 16 entries so one
bounded config file cannot amplify into an unbounded set of full-viewport frames.
The root `seed` derives stable per-position ambient sub-seeds. Config parsing rejects
unsupported versions, unknown layers, incomplete version/layer pairs, and
preset/custom ambiguity. `ResolvedConfig` then carries only the validated tuple; the
composition root copies it into `PreparedRun`, and the scene package maps names to
frozen layer values. Existing config files omit both `scene` and `layers` and retain
the exact one-text-layer path.

Effects are plain callables over `TextMask`, `RenderContext`, and frozen
`EffectConfig(seed)`. Continuous animation uses deterministic elapsed time; glitch
uses a fresh Phase 1 RNG derived from seed, fixed effect ID, and frame index. The
immutable registry is the only name-to-renderer mapping. Concrete effects never
import the registry, shell layers, I/O, clocks, or global RNG modules.

The CLI now checks an effect identifier against the registry before text/font work.
`--list-effects` reads only the immutable registry and therefore performs no config,
stdin, font, shaping, subprocess, or terminal access. `PreparedRun` continues to
contain an effect identifier rather than a renderer.

Terminal adapter decisions are recorded in [ADRs](adr/README.md). The WezTerm adapter
owns truecolor half-block encoding, terminal state, and CLI-socket viewport queries.
The application owns polling cadence, caching, and frame scheduling.

Application orchestration depends on two structural ports: `AnimationBackend`
provides viewport samples and accepts complete frames, while `MonotonicClock`
provides time and sleeping. Concrete adapters satisfy these protocols without
inheriting from application classes. The application-facing backend port deliberately
does not expose terminal restoration; the CLI composition root owns the production
backend lifecycle and cleanup.

`TextMaskCache` is application-owned and retains only the active
`TypographyKey -> TextMask` pair. Replacement is committed only after successful
rasterization and viewport-dimension validation. This bounds memory across resize
sequences without adding an LRU policy that one active run does not need.

`FixedStepScheduler` is immutable arithmetic over explicit timestamps. The runtime
uses absolute deadlines, drops missed frame indices, polls viewport on an independent
250 ms cadence, and constructs effect elapsed time only as `frame_index / fps`.
`RenderSession` is the pure composition boundary from `PreparedRun`, an explicitly
injected rasterizer, `Viewport`, and frame index to `Frame`; the synchronous loop
alone reads the clock, polls, sleeps, and presents. Neither object retains frame
history, and the application layer has no concrete rasterizer dependency.

The public FPS contract is a target presentation and effect-sampling rate from 1
through 15, with a default of 8. Shared range constants live in `core.timing`;
configuration and application validate their own boundary-specific inputs against
that single range. Only the application scheduler owns pacing. When work is late it
drops frame indices instead of replaying them; terminal backends encode, write, and
flush a presented frame without adding a second delay.

The production WezTerm adapter is a one-terminal imperative shell. Pure modules own
pane-JSON parsing and deterministic cell encoding. `cell_encoder.py` downsamples a
frame to two truecolor samples per cell and emits only quantized cells changed since
the previous frame. `viewport.py` alone runs the timeout-bounded WezTerm CLI
subprocess; `terminal_state.py` alone writes synchronized escape bytes; `backend.py`
composes them without importing application. The CLI preflights the initial pane
geometry before mutation, then enters terminal state, invokes the Phase 4 loop, and
preserves both runtime and cleanup failures when restoration also fails.

The installed command and `python -m mojit` share one outer bootstrap. Before any
Pillow or CLI import, `native_runtime.py` enables Windows default/user DLL search,
registers only the package's `_native/win_amd64` directory, loads FriBiDi by absolute
path, and retains both handles for process lifetime. This boundary never reads CWD,
scans or mutates `PATH`, downloads code, or leaks packaging concerns into core,
effects, application, or terminal adapters. The wheel is therefore explicitly tagged
`py3-none-win_amd64`.

Current-user installation is a separate release-shell boundary. The offline bundle contains
one PowerShell manager and a checksum manifest covering the manager and every wheel.
It verifies that closed inventory before creating an isolated environment under the
current user's local application directory. Only that environment's `Scripts`
directory is prepended to the user `PATH`; the machine `PATH`, system Python, and
runtime DLL search contract remain untouched. An ownership marker gates upgrades and
recursive uninstall, so the manager refuses to remove an arbitrary directory. The
same script owns install, repair, PATH registration, smoke verification, and uninstall
to keep those lifecycle rules single-sourced.

No plugin system, abstract factory, dependency-injection container, or generic
cross-terminal hierarchy is planned for v1. One structural terminal contract may be
introduced when the application runtime needs a fake backend in tests.
