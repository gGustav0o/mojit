# ADR 0005: Cell transport and target FPS

- Status: Accepted
- Date: 2026-08-24
- Supersedes: [ADR 0001](0001-terminal-graphics-protocol.md)

## Context

Direct Kitty and iTerm2 image transport did not provide reliable continuous
full-pane animation in the target Windows WezTerm environment. The application also
had two pacing policies: the fixed-step application scheduler and a hidden 100 ms
pause in the terminal backend. Consequently `--fps` did not have one precise owner or
meaning.

## Considered alternatives

- retain direct Kitty image replacement;
- build an animated GIF before presentation;
- invoke an external image tool for each run or frame;
- encode frames as truecolor terminal cells;
- keep backend throttling in addition to application scheduling.

## Decision

The production WezTerm backend uses truecolor half-block cells. Each RGBA frame is
composited over black, resized to `columns × (rows × 2)`, quantized, and represented by
foreground/background colors and half-block characters. The first frame and geometry
changes clear and repaint the cell canvas; later frames emit only changed cell runs.
Each replacement is enclosed in a synchronized terminal update.

`--fps` is the target presentation and effect-sampling rate:

- accepted range: `1..15`;
- default: `8`;
- deadline for frame `n`: `started_at + n / fps`;
- effect time for frame `n`: `n / fps`;
- late indices are skipped without a catch-up burst;
- achieved FPS may be lower than the target when work exceeds its frame period.

The application scheduler is the only pacing owner. The terminal backend encodes,
writes, and flushes one requested frame without sleeping.

## Consequences and follow-up

- Rendering remains deterministic against the target timeline even when frames are
  skipped.
- `AnimationResult` reports presented and skipped frames; live soak output reports
  achieved FPS and the skipped-frame ratio.
- The maximum is an input bound, not a throughput guarantee for every pane size.
- Terminal restoration resets attributes, shows the cursor, and leaves the alternate
  screen; there is no process-owned terminal image to delete.
