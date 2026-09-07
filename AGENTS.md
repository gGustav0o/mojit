# Agent operating guide

This file is the operational contract for autonomous work on `mojit`.
Keep it short. Product intent belongs in `docs/PRODUCT.md`, architecture in
`docs/ARCHITECTURE.md`, and execution sequencing in `docs/ROADMAP.md`.

## Read first

Before making a substantial change, read in this order:

1. `docs/PRODUCT.md` — current product direction and non-goals;
2. `docs/ROADMAP.md` — active milestone, acceptance criteria, and deferred work;
3. `docs/ARCHITECTURE.md` — current boundaries and post-v1 evolution rules;
4. `SPEC.md` — implemented v1 compatibility contract;
5. relevant accepted ADRs under `docs/adr/`;
6. relevant completed phase reports when historical evidence is needed.

Completed `PHASE_*_PLAN.md` and `PHASE_*_REPORT.md` files are historical records.
Do not rewrite them to describe new work.

## Authority and conflicts

- `docs/PRODUCT.md` defines what the project is becoming.
- `docs/ROADMAP.md` defines what to work on now.
- `SPEC.md` remains authoritative for existing v1 behavior unless an active roadmap
  item explicitly changes that behavior.
- Accepted ADRs remain authoritative for the decision they record until superseded
  by a new ADR.
- If documents conflict, prefer the narrower, newer document for new development,
  but do not silently break an existing v1 compatibility contract.

## Autonomy

Operate autonomously and prefer reversible, incremental decisions.

Do **not** ask the user about:

- local naming and code organization;
- ordinary refactors;
- test structure;
- small visual parameter choices;
- implementation details that do not alter a public contract;
- whether to continue to the next unblocked roadmap item.

Choose the simplest defensible option, record significant assumptions, verify it,
and continue.

Escalate only when:

- a decision materially changes the product direction;
- a breaking change to a user-facing CLI/configuration/compatibility contract is
  required and the roadmap does not already authorize it;
- two incompatible architectural directions have major long-term consequences and
  repository evidence is insufficient to choose;
- credentials, paid services, publication, signing, or other unavailable external
  authority is required;
- requirements are contradictory or technically infeasible.

If one task is blocked, document the blocker and continue with independent useful
work rather than waiting for the user.

## Engineering rules

- Preserve working v1 behavior unless the active roadmap item explicitly changes it.
- Prefer Functional Core / Imperative Shell and the dependency boundaries in
  `docs/ARCHITECTURE.md`.
- Keep rendering deterministic when practical: explicit time, seed, viewport, and
  inputs should be enough to reproduce a frame.
- Effects/layers must not write to the terminal, read clocks, files, environment, or
  global random state directly.
- Terminal-specific behavior belongs in adapters/shell code.
- Do not introduce a plugin system, dependency-injection container, generic backend
  hierarchy, or other speculative infrastructure without a present requirement.
- Do not add a major dependency when existing dependencies or a small amount of
  straightforward code solve the current problem adequately.
- Do not implement a native Kitty-terminal backend yet. WezTerm remains the primary
  terminal for current development. Note that WezTerm's use of the Kitty Graphics
  Protocol is an existing transport detail and is not the same thing as supporting
  the Kitty terminal application.
- Do not publish packages, create releases/tags, sign artifacts, or upload anything
  externally unless explicitly authorized.

## Work loop

For each substantial roadmap item:

1. inspect the relevant implementation, tests, docs, and git state;
2. define a bounded execution plan when the work is non-trivial;
3. implement the smallest coherent slice that advances the active milestone;
4. add or update tests for observable behavior and important invariants;
5. run the relevant fast checks while iterating;
6. run the full practical verification gate before declaring the slice complete;
7. review the diff for regressions, accidental scope growth, duplication, and
   architectural drift;
8. fix issues found by that review;
9. update current documentation and add an ADR only for a durable architectural
   decision;
10. leave the repository in a coherent working state and continue with the next
    unblocked roadmap item.

Do not stop merely to report that one small subtask is complete if the next roadmap
item can be advanced safely without user input.

## Verification

Use the repository's existing test, lint, format, compile, packaging, and live-terminal
checks as appropriate to the changed area. Prefer one repeatable local verification
entry point if the repository already provides one; if it does not, creating a thin
wrapper over existing commands is allowed when it materially reduces ambiguity.

A change is not complete merely because it compiles. For rendering changes, prefer
pure frame/mask/layer tests with fixed viewport, time, and seed. Use live WezTerm
acceptance when terminal lifecycle, geometry acquisition, or transport is affected.

Do not weaken tests or acceptance thresholds solely to make a change pass.
