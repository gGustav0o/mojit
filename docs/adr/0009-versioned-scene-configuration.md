# ADR 0009: Versioned scene configuration

- Status: Accepted
- Date: 2026-09-06

## Context

Phase 9 must let users select presets and define ordered multi-layer scenes without
exposing Python class names or weakening the strict v1 TOML contract. The first
format should be sufficient for current text, stars, rain, and snow while remaining
explicitly evolvable.

## Considered alternatives

- serialize implementation module/class names and constructor arguments;
- accept unversioned arbitrary nested dictionaries;
- use a versioned ordered array of current product layer identifiers.

## Decision

The v1 scene document extension is:

```toml
scene_version = 1
layers = ["stars", "rain", "text"]
```

Version 1 accepts `stars`, `rain`, `snow`, and `text`, in back-to-front order, and
requires exactly one text layer. It uses the existing root `seed` and each layer's
curated defaults; repeated ambient identifiers receive distinct derived sub-seeds.
The `scene` preset key and custom `scene_version`/`layers` pair are mutually
exclusive. A CLI `--scene` selection overrides a custom scene from the config file
under the existing CLI-over-file precedence.

Unknown keys, versions, layer identifiers, wrong TOML types, incomplete pairs, and
ambiguous preset/custom documents fail during pure configuration parsing, before
font, shaping, terminal, or clock work.

## Consequences and follow-up

- The format describes visual concepts and ordering without binding files to Python
  types.
- Existing v1 configuration remains valid and continues to mean a one-text-layer
  scene.
- Version 1 intentionally relies on curated layer defaults. A future format version
  may add strict per-layer visual options when concrete usability evidence justifies
  the extra surface.
- Changing the meaning of version 1 is a breaking configuration change; extend with
  a new version instead.
