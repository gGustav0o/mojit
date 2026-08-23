# P0.3 — Graphics transport

## Question

Which single WezTerm transport should v1 use for repeated frame replacement?

## Environment

See [000-environment.md](000-environment.md).

## Probe and exact commands

```powershell
python spikes\wezterm\transport_probe.py --width 1280 --height 720 --frames 12
python spikes\wezterm\transport_probe.py --width 1920 --height 1080 --frames 8
python spikes\wezterm\live_proof.py --protocol kitty --seconds 8 --fps 10
python spikes\wezterm\live_proof.py --protocol iterm --seconds 8 --fps 10
```

Offline probes emit machine-readable JSON to stdout. Live raw measurements are
retained locally as ignored `spikes/results/live-*.json`; the durable summary is
preserved below.

## Inputs and controlled variables

Kitty zlib-compressed RGBA, Kitty PNG, and iTerm2 PNG used identical deterministic
opaque, alpha-heavy, and high-change source frames at each resolution.

## Observations

At 1920 x 1080, median encode times were:

| Content | Kitty zlib RGBA | Kitty PNG | iTerm2 PNG |
|---|---:|---:|---:|
| opaque | 35.84 ms | 22.37 ms | 21.96 ms |
| alpha-heavy | 38.06 ms | 22.62 ms | 22.42 ms |
| high-change | 319.67 ms | 266.23 ms | 196.05 ms |

The 8-second Kitty live run completed 80/80 frames at 10 FPS, handled three
resizes, and left no owned placement. iTerm2 encoded slightly faster but provided no
equivalent explicit image-resource lifecycle; its observed WezTerm working-set
growth was also larger in this non-identical live comparison.

## Failure modes

Full-screen high-entropy 1080p frames cannot sustain 30 or 60 FPS with any tested
encoding. Transport throughput is content- and viewport-dependent.

## Conclusion

Use direct Kitty Graphics Protocol with PNG, chunked base64, a stable owned image
identifier, replacement placement, synchronized updates, and explicit deletion.
Default to 30 FPS. Treat 60 FPS as best effort, never as a guarantee.

## ADR impact

See ADR 0001.
