# ADR 0007: Ordered full-viewport scene composition

- Status: Accepted
- Date: 2026-09-06

## Context

Phase 7 needs one pure boundary that can preserve the existing text/effect renderer
while allowing independent ambient visuals to be combined in Phase 8. The boundary
must make ordering, viewport compatibility, and deterministic frame inputs explicit
without introducing a speculative scene graph, plugin system, or terminal hierarchy.

## Considered alternatives

- keep composition implicit inside `RenderSession` and special-case each new visual;
- introduce an ECS or general hierarchical scene graph before concrete layers exist;
- define a small ordered scene value and a structural layer rendering contract.

## Decision

Core scene composition uses:

- an immutable non-empty `Scene` containing layers in back-to-front order;
- a structural `Layer.render(RenderContext) -> Frame` contract;
- one pure `render_scene()` fold using the existing source-over compositor;
- strict full-viewport validation for every returned layer frame.

The application remains responsible for constructing `RenderContext`, typography
caching, resize observation, scheduling, and presentation. `TextEffectLayer` adapts
the v1 `TextMask + EffectConfig + Effect` contract into a scene layer, so the existing
CLI renders a one-layer scene with byte-equivalent output. Layer-specific immutable
configuration, including deterministic seeds, is captured by the layer; clocks,
terminal state, files, environment, and global RNG remain outside layers.

The scene model is currently a Python composition primitive. User-facing scene
configuration and named presets remain Phase 9 work.

## Consequences and follow-up

- Phase 8 can add procedural layers without changing terminal or scheduling code.
- Z-order is tuple order: the first layer is the backmost and each later layer is
  composited over it.
- A mismatched or non-`Frame` layer result fails before presentation.
- The one-layer path returns the layer frame unchanged, preserving v1 rendering.
- Full-viewport layer frames favor a simple deterministic contract over premature
  retained-mode or region-based optimization; Phase 10 may optimize only from
  measured evidence.
