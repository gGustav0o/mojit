# mojit

`mojit` is a Windows 11 / WezTerm CLI for displaying large animated Unicode text.

The product requirements are in [SPEC.md](SPEC.md), and dependency boundaries are
recorded in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

Phase 0 results and decisions are summarized in
[docs/PHASE_0_REPORT.md](docs/PHASE_0_REPORT.md). Phase 1's deterministic typography
core is complete; see [the plan](docs/PHASE_1_PLAN.md) and
[the report](docs/PHASE_1_REPORT.md). Phase 2's configuration and input boundary is
also complete; see [the plan](docs/PHASE_2_PLAN.md) and
[the report](docs/PHASE_2_REPORT.md). Experimental code remains isolated under
`spikes/`. Phase 3's pure compositor and deterministic effects are complete; see
[the plan](docs/PHASE_3_PLAN.md) and [the report](docs/PHASE_3_REPORT.md). Phase 4's
bounded application orchestration is complete; see [the plan](docs/PHASE_4_PLAN.md)
and [the report](docs/PHASE_4_REPORT.md). Phase 5's production WezTerm transport and
terminal lifecycle are complete; see [the plan](docs/PHASE_5_PLAN.md) and
[the report](docs/PHASE_5_REPORT.md). The remaining boundary is release packaging and
clean-machine validation.

## Runtime prerequisites

- Windows 11 and WezTerm;
- Python 3.11 or newer with the project dependencies installed;
- Pillow built with Raqm/FriBiDi support;
- a CJK font. The v1 default is `C:/Windows/Fonts/YuGothB.ttc`.

Run from an interactive WezTerm pane:

```powershell
mojit "電脳世界"
mojit "電脳世界" --vertical --effect glitch
```

`Ctrl+C` stops the continuous animation and restores the primary screen, cursor, and
owned Kitty image. Piped UTF-8 text is supported. Redirecting run-mode stdout is not.

If the process is hard-terminated or terminal output is already broken, cleanup bytes
cannot be delivered. Close the affected pane to recover its terminal state.
