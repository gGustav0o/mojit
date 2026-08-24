# Architecture boundaries

`mojit` is a small modular monolith built around Functional Core / Imperative Shell.
The physical layout is intended to enforce these dependency directions:

```text
config.models ────────────────► core.models
config.resolve ───────────────► config.models
core ─────────────────────────► no project layer
effects ──────────────────────► core
application ──────────────────► core + effects
adapters ─────────────────────► core models
cli (composition root) ───────► application + adapters + config
bootstrap ────────────────────► native runtime, then cli
```

Forbidden dependencies:

- `core` and `effects` must not import `application`, `adapters`, or `cli`;
- `core` must not accept `ResolvedConfig`; application maps it to narrow core options;
- effects must not access terminal state, files, clocks, or global random state;
- typography must not own mutable caches;
- the WezTerm adapter must not contain layout or effect policy;
- experimental `spikes` code must not be imported by `src/mojit`.

The production `TextMask` is a full-viewport alpha plane. Its origin is fixed at
`(0, 0)`; typography owns glyph placement within that plane.

Core arrays are isolated C-contiguous `uint8` buffers backed by immutable bytes.
Callers cannot mutate a `TextMask` or `Frame` through the source ndarray or by
re-enabling the stored array's write flag.

The font adapter is the filesystem boundary: it returns immutable bytes and a SHA-256
content identity. Typography receives no path or open file handle. `TypographyKey`
is both the rendering request and cache identity; it contains only values that can
change the mask.

The config-file adapter owns discovery, bounded reads, and UTF-8 decoding. The TOML
module is pure and accepts only a closed set of root-level keys. Config resolution is
an explicit field-by-field `CLI > file > defaults` operation with source-relative font
paths.

The CLI is the Phase 2 composition root. Before terminal access it resolves one-line
Unicode input, loads and validates the font, checks Raqm/FriBiDi, and creates an
immutable `PreparedRun`. That request contains values and font bytes only: no paths,
streams, parsed TOML, CLI namespaces, environment, or adapter objects.

The compositor is a pure full-viewport boundary. Transform operations accept
immutable `TextMask`/`Frame` values, use clipped transparent edges, and return new
immutable values. Pillow owns LANCZOS resize, Gaussian blur, and source-over alpha;
NumPy owns clipped translation, band displacement, and channel assembly. Effects do
not duplicate these operations.

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
`RenderSession` is the pure composition boundary from `PreparedRun`, `Viewport`, and
frame index to `Frame`; the synchronous loop alone reads the clock, polls, sleeps, and
presents. Neither object retains frame history.

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

No plugin system, abstract factory, dependency-injection container, or generic
cross-terminal hierarchy is planned for v1. One structural terminal contract may be
introduced when the application runtime needs a fake backend in tests.
