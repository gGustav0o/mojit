# mojit

`mojit` is a Windows 11 / WezTerm CLI for displaying large animated Unicode text.

The product requirements are in [SPEC.md](SPEC.md). The dependency boundaries are
recorded in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), and the current discovery
work is defined by [docs/PHASE_0_PLAN.md](docs/PHASE_0_PLAN.md).

Phase 0 results and decisions are summarized in
[docs/PHASE_0_REPORT.md](docs/PHASE_0_REPORT.md). Phase 1's deterministic typography
core is complete; see [the plan](docs/PHASE_1_PLAN.md) and
[the report](docs/PHASE_1_REPORT.md). Phase 2's configuration and input boundary is
also complete; see [the plan](docs/PHASE_2_PLAN.md) and
[the report](docs/PHASE_2_REPORT.md). Experimental code remains isolated under
`spikes/`. Phase 3's pure compositor and deterministic effects are complete; see
[the plan](docs/PHASE_3_PLAN.md) and [the report](docs/PHASE_3_REPORT.md). Phase 4's
bounded application orchestration is complete; see [the plan](docs/PHASE_4_PLAN.md)
and [the report](docs/PHASE_4_REPORT.md). The next boundary is the production WezTerm
transport and terminal lifecycle.
