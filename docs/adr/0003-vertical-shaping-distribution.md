# ADR 0003: Vertical shaping distribution

- Status: Accepted
- Date: 2026-08-23

## Context

Pillow's vertical `direction="ttb"` path requires Raqm and FriBiDi. The Windows
Pillow wheel alone did not provide a self-contained capability on the reference
machine: it succeeded only because unrelated software exposed FriBiDi through
`PATH`.

## Considered alternatives

- Pillow/FreeType/Raqm with an application-controlled FriBiDi runtime;
- requiring a user-installed FriBiDi DLL on `PATH`;
- manual per-character vertical layout;
- disabling vertical layout when the dependency is absent.

## Evidence

See [P0.0](../../spikes/results/000-environment.md) and
[P0.1](../../spikes/results/001-typography.md). Raqm output was deterministic and
visually acceptable. The BASIC layout engine rejected vertical direction.

## Decision

v1 uses Pillow/FreeType/Raqm with `direction="ttb"` and `language="ja"`. Release
artifacts must include an application-controlled, versioned FriBiDi Windows runtime
and its required license notices. The composition root makes its DLL directory
available before importing Pillow's native text stack. It enables secure default/user
DLL search, loads the packaged DLL by absolute path, and retains both handles for the
process lifetime. This prevents an earlier same-named DLL on `PATH` from shadowing
the packaged runtime.

Startup checks Raqm and FriBiDi capability before terminal mutation. Missing support
is a fatal, actionable error. There is no manual vertical fallback in v1.

## Consequences and follow-up

- Packaging must pin the FriBiDi source/version, checksum, license text, and build or
  acquisition recipe.
- CI must test a clean Windows image with ambient third-party DLL directories removed.
- Source development may use a system FriBiDi, but passing locally through unrelated
  `PATH` entries is not release evidence.
- Phase 6 pins FriBiDi 1.0.16, retains the complete upstream source, and verifies
  byte-reproducible MSVC `/Brepro` builds plus CPython 3.11-3.14 artifact installs.

## References

- [Pillow: building from source](https://pillow.readthedocs.io/en/stable/installation/building-from-source.html)
- [GNU FriBidi releases](https://github.com/fribidi/fribidi/releases)
