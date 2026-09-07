# ADR 0008: Stateless procedural ambience

- Status: Accepted
- Date: 2026-09-06

## Context

Phase 8 needs rain, stars, and snow that remain deterministic, resize cleanly, and
run indefinitely without growing particle history. A retained simulation would need
additional lifecycle, resize migration, catch-up, and serialization rules before the
product has a concrete need for inter-frame physics.

## Considered alternatives

- retain and advance mutable particle objects between presented frames;
- keep viewport-sized simulation history and migrate it during resize;
- regenerate a bounded seeded field for each explicit render context.

## Decision

Initial procedural ambience layers are frozen configuration values and retain no
runtime particle state. Each render:

1. derives a fresh local PCG64 generator from the layer seed and a stable layer ID;
2. generates stable particle attributes for the current viewport;
3. derives positions and opacity from explicit `RenderContext.elapsed_seconds`;
4. clips drawing into one transparent full-viewport frame;
5. caps generated particles at 4,096 per layer.

Density remains viewport-relative below the cap. Resize therefore rebuilds the field
for the new dimensions without stale buffers, while returning to a previous viewport
and time reproduces the same frame. Layers never access clocks, terminal state,
files, environment, or global random state.

## Consequences and follow-up

- Memory retained across frames is constant and limited to immutable configuration.
- Skipped presentation indices do not require simulation catch-up; explicit elapsed
  time selects the visual state directly.
- The initial primitives favor ambient motion over particle interactions or physical
  continuity across resize.
- Full-frame regeneration and compositing costs must be measured during Phase 10;
  optimization requires evidence and must preserve deterministic output.
