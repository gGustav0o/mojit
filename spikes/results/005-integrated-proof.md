# P0.5 — Integrated proof

## Question

Do the typography, viewport, transport, resize, and lifecycle choices work together?

## Environment

See [000-environment.md](000-environment.md).

## Probe and exact command

```powershell
python spikes\wezterm\integrated_suite.py `
  --font C:\Windows\Fonts\YuGothB.ttc `
  --seconds 300 --fps 30 --vertical
```

Raw measurements: `spikes/results/integrated-proof-5min.json`.

## Inputs and controlled variables

A deterministic vertical CJK pulse ran in an isolated WezTerm window. The suite
performed repeated split-pane resize transitions and restored twice on exit.

## Observations

- duration: 300.000 s;
- frames: 9,000;
- achieved rate: 29.99997 FPS;
- frame time: median 5.725 ms, p95 7.559 ms, max 30.266 ms;
- resize observations: 12;
- bytes written: 220,384,776;
- WezTerm working-set delta: +151,552 bytes;
- exit code: 0; orchestration error: none;
- primary terminal state and cursor were restored.

## Failure modes

This proves the reference environment and structured pulse workload, not arbitrary
high-entropy effects, every display topology, or clean-machine dependency packaging.

## Conclusion

The selected mechanisms work together for the v1 reference workload at the chosen
30 FPS default without observed resource accumulation.

## ADR impact

The integrated result supports ADRs 0001–0004 and closes the runtime portion of the
Phase 0 gate.
