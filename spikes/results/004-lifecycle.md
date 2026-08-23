# P0.4 — Terminal lifecycle

## Question

Can all owned terminal state be restored after normal exit, failure, and interrupt?

## Environment

See [000-environment.md](000-environment.md).

## Probe and exact command

```powershell
python spikes\wezterm\lifecycle_suite.py --parent-pane-id 2
```

Per-case raw measurements are retained locally as ignored
`spikes/results/lifecycle-*.json`; the durable summary is preserved below.

## Inputs and controlled variables

Normal completion, injected failure, and interrupt ran in disposable panes. Each
case invoked restore twice and verified state before the host pane was closed.

## Observations

All cases restored the primary screen, visible cursor, synchronized-update mode,
and owned Kitty image/placement. Parent dimensions returned to their exact initial
values. Repeated restore was harmless.

## Failure modes

If the output channel is already physically broken, no process can deliver cleanup
escape sequences through it. Closing the affected pane/process is the recovery path.
Abrupt process termination (`TerminateProcess`, power loss) has the same limitation.

## Conclusion

Own terminal mutation in one context-managed shell, restore in `finally`, make
restore idempotent, and use one process-owned image identifier. Document hard
termination and broken-output recovery instead of claiming an impossible guarantee.

## ADR impact

See ADR 0001. The lifecycle policy is part of the WezTerm adapter boundary.
