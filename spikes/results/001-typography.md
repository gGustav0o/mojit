# P0.1 — Vertical typography

## Question

Can Pillow render acceptable vertical Japanese text deterministically?

## Environment

See [000-environment.md](000-environment.md).

## Probe and exact command

```powershell
python spikes\typography\vertical_probe.py `
  --font C:\Windows\Fonts\YuGothB.ttc `
  --output-dir spikes\results\typography `
  --iterations 20
```

The probe emits machine-readable JSON to stdout. Visual evidence is versioned under
`spikes/results/typography/`; the measurement summary is preserved below.

## Inputs and controlled variables

The same font, corpus, canvas, language `ja`, and iteration count were used for
horizontal and `direction="ttb"` rendering.

## Observations

| Mode | Median | p95 | Deterministic repeat |
|---|---:|---:|---|
| horizontal | 2.155 ms | 2.888 ms | yes |
| vertical | 1.763 ms | 2.726 ms | yes |

The rendered bounds did not clip. Japanese punctuation, brackets, and prolonged
sound marks were visually acceptable in the selected font. Pillow's BASIC layout
engine rejected vertical direction, confirming that Raqm is required.

## Failure modes

- Invalid or missing fonts fail at load time.
- Without FriBiDi, Raqm and `direction="ttb"` are unavailable.

## Conclusion

Use Pillow/FreeType with Raqm, `direction="ttb"`, and `language="ja"`. Validate the
font and shaping capability before entering terminal state. Do not implement a
manual per-character vertical fallback in v1.

## ADR impact

See ADR 0003 and ADR 0004.
