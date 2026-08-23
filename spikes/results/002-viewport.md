# P0.2 — Pixel viewport and stdin isolation

## Question

How can the current WezTerm pane size be obtained without sharing stdin with text?

## Environment

See [000-environment.md](000-environment.md).

## Probe and exact commands

```powershell
python spikes\wezterm\viewport_probe.py --iterations 20
"少女終末旅行" | python spikes\wezterm\viewport_probe.py --iterations 20 --consume-stdin
python spikes\wezterm\resize_probe.py --pane-id 2 --iterations 20
```

The probes emit machine-readable JSON to stdout. The durable measurement summary is
preserved below; disposable raw output is intentionally not versioned.

## Inputs and controlled variables

Queries targeted the pane named by `WEZTERM_PANE`. Resize testing alternated a
disposable split pane and compared the parent's before/after dimensions.

## Observations

- `wezterm cli list --format json` returned rows, columns, pixel width, pixel height,
  and DPI over WezTerm's separate CLI socket.
- Static query latency: median 27.09 ms, p95 73.96 ms.
- Piped UTF-8 text remained intact and did not compete with terminal replies.
- Twenty grow/shrink transitions were observed; the parent returned exactly to
  `94 x 44` cells and `940 x 1012` pixels.
- A newly created window reported DPI `0` while its pixel dimensions were valid.

## Failure modes

The CLI may time out, return malformed JSON, omit the requested pane, or transiently
fail during a topology change. DPI is not reliable enough for layout.

## Conclusion

Use `wezterm cli list --format json`, select `WEZTERM_PANE`, and poll outside the
frame loop at approximately 250 ms. Require valid positive pixel/cell dimensions at
startup; during animation retain the last known valid viewport after a transient
failure. Read piped application text as UTF-8 independently.

## ADR impact

See ADR 0002.
