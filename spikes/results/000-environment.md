# P0.0 — Reference environment

## Question

Which concrete environment was used for Phase 0 measurements?

## Environment

- Windows 11 `10.0.26200.9168`;
- WezTerm `20240203-110809-5046fc22`;
- Python `3.13.3`;
- Pillow `12.3.0`, FreeType `2.14.3`, Raqm `0.10.5`;
- NumPy `2.2.5`;
- AMD Ryzen 7 4800H, 16 logical processors;
- reference pane: `94 x 44` cells, `940 x 1012` pixels, 96 DPI;
- font: `C:\Windows\Fonts\YuGothB.ttc`, 14,729,372 bytes,
  SHA-256 `d923a57f781f06198167da4f58287be7ac64a954a47aff4295e078a42b4b68b2`.

## Probe and exact command

```powershell
python -m pip install -r spikes\requirements-phase0.txt
python spikes\environment_probe.py
wezterm cli list --format json
```

The probe emits machine-readable JSON to stdout. The durable measurement record is
this file; disposable raw output is intentionally not versioned.

## Inputs and controlled variables

The typography corpus was `電脳世界`, `警告、「猫」。`, and `「スーパー（猫）」ー。`.
The font path and checksum were fixed for all typography probes.

## Observations

Pillow reported Raqm only while a FriBiDi DLL from unrelated installed software was
visible through `PATH`. With a sanitized Windows/Python-only `PATH`, Raqm capability
was unavailable.

## Failure modes

- Windows Japanese supplemental fonts are optional and may be absent.
- The Pillow Windows wheel does not make FriBiDi availability self-contained.

## Conclusion

The reference machine is suitable for measurement, but its ambient `PATH` is not a
valid distribution strategy. Font and FriBiDi checks must run before animation.

## ADR impact

See ADR 0003 and ADR 0004.
