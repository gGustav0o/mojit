# ADR 0001: WezTerm graphics protocol

- Status: Superseded by [ADR 0005](0005-cell-transport-and-fps.md)
- Date: 2026-08-23

## Context

v1 needs one direct graphics transport with predictable replacement and cleanup.

## Considered alternatives

- Kitty Graphics Protocol with PNG;
- Kitty Graphics Protocol with zlib-compressed RGBA;
- iTerm2 inline images;
- a `wezterm imgcat` subprocess per frame.

## Evidence

See [P0.3](../../spikes/results/003-transport.md) and
[P0.5](../../spikes/results/005-integrated-proof.md). PNG was materially smaller and
faster than zlib RGBA on representative structured frames. Kitty uniquely supplied
the explicit image deletion and replacement lifecycle needed by the application.

## Decision

The WezTerm adapter uses direct Kitty Graphics Protocol with:

- PNG payloads (`f=100`) and chunked base64 transfer;
- one stable process-owned image ID and replacement placement;
- placement sized to the current cell viewport;
- cursor-independent placement (`C=1`);
- synchronized updates around presentation;
- quiet successful replies while preserving protocol errors (`q=1`);
- explicit deletion by image ID during idempotent restore.

The default is 30 FPS. `--fps 60` is a target requested by the user, not a guarantee.
Effects must avoid assuming that full-screen high-entropy 1080p frames are cheap.

Production preflight proves the target through an interactive binary stdout,
`WEZTERM_PANE`, and one timeout-bounded exact-pane
`wezterm cli list --format json` call. v1 does not emit a Kitty capability query and
read its reply: terminal input may be the user's piped text and remains isolated.

## Consequences and follow-up

- Protocol encoding and terminal state remain private to `adapters.wezterm`.
- Production startup must perform the bounded exact-pane WezTerm preflight above.
- The application scheduler may drop lateness; the renderer remains deterministic by
  frame index.
- `imgcat` may be used diagnostically, never as the frame path.
- A physically broken output channel or hard process termination cannot receive
  cleanup bytes; closing the pane is the documented recovery.
