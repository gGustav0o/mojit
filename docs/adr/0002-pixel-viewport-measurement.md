# ADR 0002: Pixel viewport measurement

- Status: Accepted
- Date: 2026-08-23

## Context

The application needs drawable pixel dimensions after resize while stdin may contain
the user's text. Terminal reply sequences would share and corrupt that input channel.

## Considered alternatives

- terminal cell/pixel query sequences;
- Win32/ConPTY-derived dimensions;
- WezTerm's CLI socket and pane metadata.

## Evidence

See [P0.2](../../spikes/results/002-viewport.md). `wezterm cli list --format json`
returned the required dimensions through a separate channel, preserved piped UTF-8
input, and tracked repeated split-pane resizes.

## Decision

The v1 adapter:

1. reads the target pane ID from `WEZTERM_PANE`;
2. invokes `wezterm cli list --format json` with a two-second timeout;
3. selects that exact pane and validates positive rows, columns, pixel width, and
   pixel height;
4. polls approximately every 250 ms, independently of frame presentation;
5. fails before animation if no initial viewport is available;
6. retains the last valid viewport during a transient runtime query failure.

DPI is diagnostic only and does not participate in layout.

## Consequences and follow-up

- Viewport acquisition is intentionally WezTerm-specific.
- Stdin is reserved exclusively for application input.
- Production tests need fake CLI responses for timeout, malformed JSON, missing pane,
  and transient failure.
- Query frequency is bounded and never scales with FPS.
