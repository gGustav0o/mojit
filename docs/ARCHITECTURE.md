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

Phase 0 adapter decisions are recorded in [ADRs](adr/README.md). The WezTerm adapter
owns Kitty protocol encoding, terminal state, and CLI-socket viewport queries. The
application owns polling cadence, caching, and frame scheduling.

No plugin system, abstract factory, dependency-injection container, or generic
cross-terminal hierarchy is planned for v1. One structural terminal contract may be
introduced when the application runtime needs a fake backend in tests.
