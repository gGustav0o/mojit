# ADR 0004: Default CJK font

- Status: Accepted
- Date: 2026-08-23

## Context

The CLI needs a deterministic default, but Japanese supplemental fonts are optional
Windows features and Microsoft font files must not be redistributed casually.

## Considered alternatives

- bundle a third-party CJK font;
- discover arbitrary system fonts;
- use a fixed Windows Japanese font path with explicit fallback instructions;
- require `--font` for every invocation.

## Evidence

See [P0.0](../../spikes/results/000-environment.md). `YuGothB.ttc` rendered the fixed
corpus correctly, but its presence is not universal across clean Windows installs.

## Decision

Font resolution order is:

1. CLI `--font`;
2. configured font path;
3. `C:\Windows\Fonts\YuGothB.ttc`.

v1 does not bundle or generally discover fonts. The resolved file is loaded and
validated against the requested text/orientation before terminal mutation. If the
default is absent, the error tells the user to install Windows Japanese Supplemental
Fonts or pass `--font`/configure a CJK font.

## Consequences and follow-up

- The no-argument font path works only where the Windows Japanese font is installed.
- Acceptance CI must provision that optional Windows capability explicitly.
- Future bundling of an open CJK font requires a separate ADR and size/license review.

## References

- [Microsoft: Windows 11 font list](https://learn.microsoft.com/en-us/typography/fonts/windows_11_font_list)
- [Microsoft: add missing supplemental fonts](https://learn.microsoft.com/en-us/windows/deployment/windows-missing-fonts)
