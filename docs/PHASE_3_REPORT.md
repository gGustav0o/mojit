# Phase 3 report

- Status: Complete
- Date: 2026-08-23
- Scope: pure compositor and deterministic v1 effects

## Delivered

| Area | Result |
|---|---|
| Compositor | Full-viewport translate, scale, blur, colorize, source-over, channel merge, and band warp |
| Pixel contract | Straight-alpha `uint8` sRGB, transparent clipping, no wrap-around |
| Effect API | Frozen `EffectConfig(seed)` and plain callable alias |
| Effects | `neon`, `pulse`, `chromatic`, deterministic `glitch` |
| Registry | Immutable exact lookup with stable alphabetical listing |
| CLI | Unknown-effect preflight and successful isolated `--list-effects` |
| Boundaries | Static tests reject shell/I/O/global-RNG imports from effects |

No effect owns mutable state. Public compositor/effect results reuse the immutable
`TextMask` and `Frame` contracts from Phase 1.

## Reference evidence

Reference inputs:

```text
font:       C:\Windows\Fonts\YuGothB.ttc
font SHA:   d923a57f781f06198167da4f58287be7ac64a954a47aff4295e078a42b4b68b2
viewport:   640 x 384
margin:     0.08
frame:      17
elapsed:    17 / 30 seconds
seed:       42
Pillow:     12.3.0
```

Frame SHA-256 values:

| Orientation | Effect | RGBA SHA-256 |
|---|---|---|
| horizontal | chromatic | `059286d5b64ce18ac1ae02238c1462c42bc6158015bc8df7d266fb00761f9bce` |
| horizontal | glitch | `7259d422d4a7d2b73771f9cc9a0896d3e5a170ad511af71ca589d2ee6d9cdeac` |
| horizontal | neon | `d99852907bbea94860114370ce3c234a57c24b57c69a452404c58343d3a11e3e` |
| horizontal | pulse | `a38586dd35d2a1cdac54a0cdbbd1a00d349654ebd1cfb810eb99ed1e0e613c1d` |
| vertical | chromatic | `ffc6e6847c15da24e902af1c9ffdd98c5542c1e3d35f5eebb8ccd28c555d4af2` |
| vertical | glitch | `1f80dd42eec1d78bbf84b8851dddeae9671551db8ba517b68c646ecb50312fb3` |
| vertical | neon | `f6791a63d143880319303462e5faaed99a25d2193eb8cd725291aced4eb9f58a` |
| vertical | pulse | `021b770855889dc0cde1ff94d6f158812fd4be42899dc71060eb03fa72c956a0` |

All eight reference frames were visually inspected. CJK glyph structure remained
readable, glow stayed inside the viewport, and displaced pixels clipped without
wrapping.

## Gate results

```text
pytest:                    308 passed
focused phase coverage:    99.64% (required >= 95%)
ruff check:                passed
ruff format --check:       passed
compileall:                passed
reference effects:         8 passed, 0 skipped
```

## Deferred by design

- application-owned `TextMask` cache;
- scheduler and animation loop;
- resize polling;
- terminal state and Kitty PNG transport;
- long-running cleanup and `Ctrl+C` integration.

These remain outside Phase 3. The next boundary is application orchestration over
the completed typography and effect pipeline.
