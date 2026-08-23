# Phase 0 report

- Status: Architecture and runtime risks closed; release packaging verification deferred
- Date: 2026-08-23
- Reference platform: Windows 11 / WezTerm

## Gate

| Criterion | Result | Evidence |
|---|---|---|
| Vertical Japanese shaping | Passed | [P0.1](../spikes/results/001-typography.md) |
| Viewport with positional/piped input | Passed | [P0.2](../spikes/results/002-viewport.md) |
| Transport performance/resource lifecycle | Passed at default 30 FPS | [P0.3](../spikes/results/003-transport.md) |
| Restore after normal/failure/interrupt | Passed | [P0.4](../spikes/results/004-lifecycle.md) |
| Five-minute integrated proof | Passed: 9,000 frames, 12 resize observations | [P0.5](../spikes/results/005-integrated-proof.md) |
| Long-lived decisions recorded | Passed | [ADRs](adr/README.md) |
| Clean-Windows FriBiDi packaging | Verification assigned to packaging | [ADR 0003](adr/0003-vertical-shaping-distribution.md) |

## Frozen production decisions

- Kitty Graphics Protocol with PNG and explicit resource deletion;
- `wezterm cli list --format json` through the CLI socket for viewport measurement;
- Pillow/Raqm vertical shaping with an application-controlled FriBiDi runtime;
- fixed default `YuGothB.ttc` path with actionable failure if unavailable;
- 30 FPS default; 60 FPS best effort;
- `TextMask` always occupies the full viewport coordinate space.

## Explicit release gates

- Pin and package FriBiDi with license/checksum/build provenance.
- Verify vertical startup in clean Windows CI without ambient third-party DLLs.
- Provision Japanese Supplemental Fonts in acceptance CI or supply `--font`.

These are packaging work derived from Phase 0, not unresolved architectural choices.
Phase 0 does not claim that a release artifact already exists.
