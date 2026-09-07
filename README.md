# mojit

`mojit` is a Windows-first terminal visual engine. The released v1 baseline is a
Windows 11 / WezTerm CLI for displaying large animated Unicode text; current
development is evolving that proven renderer into a lightweight composable terminal
scene and ambience engine with Japanese typography as a first-class visual primitive.

For current development, read:

- [docs/PRODUCT.md](docs/PRODUCT.md) — what the project is becoming;
- [docs/ROADMAP.md](docs/ROADMAP.md) — what to build next;
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — dependency boundaries and evolution
  rules;
- [AGENTS.md](AGENTS.md) — autonomous-agent operating rules.

[SPEC.md](SPEC.md) is the implemented **v1 compatibility contract**, not the complete
post-v1 product vision. Completed Phase 0-6 plans/reports and accepted ADRs preserve
the evidence and decisions that produced that baseline; they should not be rewritten
retroactively for new development.

The current roadmap deliberately keeps Windows + WezTerm as the primary environment.
A native Kitty-terminal backend is a possible later direction, after scene composition
and ambient functionality are mature. WezTerm's existing use of the Kitty Graphics
Protocol is a transport detail and does not mean that the Kitty terminal application
is currently supported.

## Runtime prerequisites

- Windows 11 and WezTerm;
- CPython 3.11-3.14 x64;
- the verified Phase 6 wheelhouse (BudouX, Pillow/Raqm, and FriBiDi are self-contained
  there);
- a CJK font. The v1 default is `C:/Windows/Fonts/YuGothB.ttc`.

## Install for the current Windows user

Build the release candidate when working from the source checkout, then extract its
offline bundle:

```powershell
.\tools\release\build_artifacts.ps1
Expand-Archive .\dist\release\mojit-1.0.0-windows-x64-wheelhouse.zip .\mojit-wheelhouse
```

Verify the ZIP against `dist/release/SHA256SUMS.txt`:

```powershell
$archive = Resolve-Path .\dist\release\mojit-1.0.0-windows-x64-wheelhouse.zip
$expected = (Select-String -LiteralPath .\dist\release\SHA256SUMS.txt -Pattern "  $([IO.Path]::GetFileName($archive))$").Line.Split(" ")[0]
$actual = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $expected) { throw "Release archive checksum mismatch" }
```

If the bundle was downloaded, unblock the verified installer, then run it without
administrator privileges:

```powershell
Unblock-File .\mojit-wheelhouse\install.ps1
& .\mojit-wheelhouse\install.ps1
```

The installer selects the newest 64-bit CPython 3.11-3.14 known to the Windows Python
launcher, falling back to `python.exe` on `PATH`. It creates an isolated environment
under `%LOCALAPPDATA%\Programs\mojit`, installs only from the verified wheelhouse,
and adds its `Scripts` directory to the current user's `PATH`. Restart WezTerm once
after the first installation. `mojit` can then be called from any directory:

```powershell
mojit --list-effects
mojit --list-scenes
mojit "電脳世界"
mojit "雨の夜" --scene rainy-night
mojit -h
```

Built-in post-v1 ambient scenes currently include:

- `rainy-night` — slanted blue rain over a sparse night sky;
- `snowfall` — slow drifting snow with a quiet star background;
- `space` — a denser field of large, slowly twinkling stars.

The ordinary text command remains the default; selecting a scene simply composes
deterministic ambient layers behind the same text/effect rendering path. The optional
TOML key `scene = "rainy-night"` follows the existing `CLI > config file > defaults`
precedence.

A custom ordered scene uses the strict versioned form below. Layer order is back to
front; version 1 requires exactly one `text` layer and permits at most 16 layers:

```toml
scene_version = 1
layers = ["stars", "rain", "text"]
```

If neither automatic source resolves to a supported interpreter, provide one
explicitly:

```powershell
& .\mojit-wheelhouse\install.ps1 -Python C:\Path\To\Python313\python.exe
```

Run the same installer again to upgrade or repair the installation. Uninstall using
the protected copy stored with the application:

```powershell
& "$env:LOCALAPPDATA\Programs\mojit\install.ps1" -Uninstall
```

The installer changes only the current user's `PATH`; it never modifies the machine
`PATH` or requires elevation. The application wheel remains Windows x64 only and
loads its packaged FriBiDi by absolute path; the runtime itself never scans or
modifies `PATH`.

Run from an interactive WezTerm pane:

```powershell
mojit "電脳世界"
mojit "電脳世界" --vertical --effect glitch
mojit "警告" --fps 15
```

`--fps` is a target presentation and effect-sampling rate in the range `1..15`; the
default is `8`. Late frame indices are skipped rather than replayed, so the achieved
rate can be lower when rendering or terminal output is expensive.

`Ctrl+C` stops the continuous animation and restores the primary screen, cursor, and
terminal attributes. Piped UTF-8 text is supported. Redirecting run-mode stdout is not.

If the process is hard-terminated or terminal output is already broken, cleanup bytes
cannot be delivered. Close the affected pane to recover its terminal state.

## Reproduce and verify

```powershell
.\tools\release\build_fribidi.ps1
.\tools\release\build_artifacts.ps1
.\tools\release\verify_artifacts.ps1
```

The project is MIT-licensed. FriBiDi remains LGPL-2.1-or-later and separately
replaceable; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
