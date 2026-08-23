# Phase 1 report

- Status: Complete
- Date: 2026-08-23
- Scope: deterministic typography core

## Delivered

| Area | Result |
|---|---|
| Core models | Validated `Viewport`, `TextMask`, `Frame`, and `RenderContext` |
| Array contract | Owned C-contiguous `uint8` storage backed by immutable bytes |
| Randomness | Stable BLAKE2b derivation and local NumPy PCG64 generators |
| Layout | Pixel margins, ink-bearing correction, centering, and logarithmic size search |
| Font boundary | Explicit path loading, validation, bytes, and SHA-256 identity |
| Typography | Pillow/Raqm horizontal and vertical full-viewport masks |
| Cache identity | Frozen `TypographyKey` covering every mask-affecting input |
| Boundaries | Automated checks prevent core-to-outer-layer and production-to-spike imports |

## Reference evidence

Reference font:

```text
C:\Windows\Fonts\YuGothB.ttc
SHA-256: d923a57f781f06198167da4f58287be7ac64a954a47aff4295e078a42b4b68b2
```

At `640 x 384`, margin `0.08`, Pillow `12.3.0`:

| Corpus | Orientation | Mask SHA-256 |
|---|---|---|
| `電脳世界` | horizontal | `e8ebd18622031f116cf3923a4ad5e61491465a56f4b2576bff145ee307db55d4` |
| `警告、「猫」。` | vertical | `21e3891463598eda610c46aab678c27b8e6b63f9df37e4e4f2755bc057d56b03` |

Both paths were repeated deterministically and verified at `320 x 240`, `640 x 384`,
and `800 x 600`. All nonzero pixels remained inside the reserved margins.

## Gate results

```text
pytest:           82 passed
phase coverage:   95.83%
ruff check:       passed
ruff format:      passed
compileall:       passed
reference tests:  4 passed, 0 skipped
```

## Corrected Phase 0 evidence

The previously transcribed Yu Gothic checksum contained an error. Phase 1 compared
the recorded value with `Get-FileHash`, detected the mismatch before accepting a
skip, and corrected `spikes/results/000-environment.md` to the value above.

## Deferred by design

- config and CLI input resolution;
- mutable application-owned mask cache;
- effects and compositor;
- animation runtime and scheduler;
- production WezTerm adapter;
- FriBiDi release packaging.

These remain outside Phase 1. Phase 2 begins with config and input resolution.
