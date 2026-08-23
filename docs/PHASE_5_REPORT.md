# Phase 5 report: production WezTerm shell

Status: complete.

## Result

The normal CLI now composes the Phase 4 application runtime with a production
WezTerm backend and a system monotonic clock. Rendering uses deterministic Pillow PNG
encoding and direct chunked Kitty Graphics Protocol output. Exact-pane discovery,
terminal mutation, cleanup, and exit-code policy remain isolated in the imperative
shell.

Implemented boundaries:

- `viewport.py`: strict `WEZTERM_PANE`, bounded exact `wezterm cli list`, JSON and
  pixel/cell geometry validation;
- `png_encoder.py`: immutable `Frame` to deterministic RGBA PNG;
- `kitty_protocol.py`: bounded base64 command iterator, stable process image ID, and
  exact quiet deletion;
- `terminal_state.py`: alternate screen, cursor, synchronized-update, partial-write,
  idempotent restore, and retryable cleanup state machine;
- `backend.py`: cached preflight geometry, transient resize retention, PNG/Kitty
  presentation, and no frame/payload history;
- `clock.py` and `cli.py`: production composition, normal `Ctrl+C`, and combined
  primary/cleanup diagnostics.

The application layer was not changed and does not import adapters, subprocess,
clock, or CLI policy.

## Contract clarification from live evidence

WezTerm `20240203-110809-5046fc22` reports `size.dpi = 0` for a newly created pane.
This is an unavailable-DPI sentinel, not usable layout geometry. The adapter now
normalizes this observed raw value to `None`; positive finite DPI remains diagnostic
only, and pixel dimensions remain the sole layout input. Negative, non-finite, and
non-numeric values are rejected.

## Offline gate

Reference commands:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m pytest `
  --cov=mojit.adapters.wezterm --cov=mojit.adapters.clock --cov=mojit.cli `
  --cov-fail-under=95
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m ruff format --check src tests
.\.venv\Scripts\python.exe -m compileall -q src tests
```

Results on 2026-08-23:

- full suite: `484 passed`;
- target coverage: `97.30%`;
- Ruff lint and format: passed;
- bytecode compilation: passed;
- offline 1,000-frame transport soak: passed with a non-retaining output sink;
- PNG emitted through terminal commands decodes back to the exact source RGBA.

The failure matrix covers preflight, entry, presentation, PNG/protocol production,
runtime polling, interrupt, restore, partial writes, flush failures, and simultaneous
primary plus cleanup failures.

## Live WezTerm gate

Environment:

```text
OS:       Microsoft Windows NT 10.0.26200.0
WezTerm:  20240203-110809-5046fc22
Python:   3.13.3
Pillow:   12.3.0
Raqm:     0.10.5
FriBiDi:  1.0.16
Font:     C:/Windows/Fonts/YuGothB.ttc
```

The gate ran production modules in pane `15` of a disposable WezTerm window with
pane `16` as the resize neighbor. Both panes were closed after acceptance.

Commands:

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\live\wezterm_acceptance.py -m wezterm_live -q -s

.\.venv\Scripts\python.exe -m mojit "電脳世界"
# real Ctrl+C sent to the disposable pane

.\.venv\Scripts\python.exe -m pytest `
  tests\live\wezterm_acceptance.py -m wezterm_live `
  -k structured_soak -p no:cacheprovider -q -s
```

Observed results:

- horizontal and vertical CJK rendering: passed;
- injected runtime failure: cleanup passed;
- repeated restore: no additional terminal bytes;
- production CLI plus real `Ctrl+C`: exit code `0`;
- post-case state: primary screen, visible cursor, no retained owned image;
- four alternating resizes: four viewport changes detected;
- five-minute soak: `1 passed, 3 deselected in 302.36s`.

Structured soak metrics:

| Metric | Value |
|---|---:|
| Duration | 300.0 s |
| Presented frames | 4,253 |
| Average presentation latency | 7.021 ms |
| Maximum observed presentation latency | 1,060.276 ms |
| Terminal bytes streamed | 301,874,264 |
| Maximum individual write | 4,158 bytes |
| Resize attempts / detected changes | 4 / 4 |
| WezTerm working set before | 239,755,264 bytes |
| WezTerm working set after | 255,389,696 bytes |
| Observed working-set delta | +15,634,432 bytes |

The working-set delta is recorded as an observation, not a general leak bound. The
adapter itself retains only the latest geometry and lifecycle state; offline soak
tests enforce the absence of frame, payload, or output history.

## Operational limits

Cleanup is guaranteed only while the process can still write to the terminal. A hard
process termination, power loss, closed pane, or already broken output channel can
prevent restoration bytes from being delivered. Closing the affected pane is the
documented recovery.

Release artifacts, bundled FriBiDi/Raqm dependencies, signing, installer construction,
and clean-Windows validation remain outside Phase 5.
