# Architecture boundaries

`mojit` is a small modular monolith built around Functional Core / Imperative Shell.
The physical layout is intended to enforce these dependency directions:

```text
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

Phase 0 adapter decisions are recorded in [ADRs](adr/README.md). The WezTerm adapter
owns Kitty protocol encoding, terminal state, and CLI-socket viewport queries. The
application owns polling cadence, caching, and frame scheduling.

No plugin system, abstract factory, dependency-injection container, or generic
cross-terminal hierarchy is planned for v1. One structural terminal contract may be
introduced when the application runtime needs a fake backend in tests.
