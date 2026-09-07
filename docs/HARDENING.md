# Scene-engine hardening evidence

Status: current release-readiness audit, 2026-09-08.

This document records the independent review of the Phase 7-10 implementation. It is
not a replacement for the v1 contract in `SPEC.md` or the sequencing in `ROADMAP.md`.

## Verified findings and disposition

1. **Source CI was absent — fixed.** The Windows workflow calls the same
   `tools/verify.ps1` gate used by developers on CPython 3.11 and 3.14. Live graphical
   WezTerm tests remain manual. The workflow definition is locally reviewed; its first
   hosted run cannot occur until the change is pushed.
2. **`mojit.rar` was accidentally tracked — fixed.** It is deleted, archive patterns
   are ignored, and the source gate rejects a present tracked ZIP/RAR.
3. **The live soak measured WezTerm, not mojit — fixed.** It now records the Python
   renderer process working set/private bytes separately from `wezterm-gui`.
4. **Longevity tests only bounded logical state — fixed as an evidence gap.** The
   standalone `tools/scene_soak.py` performs configurable sustained process sampling.
   Automated tests validate its instrumentation but intentionally set no short-window
   pseudo-leak threshold. A long run still requires manual interpretation.
5. **Scene composition retained avoidable full-frame inputs — fixed.** Layer frames
   are streamed into the compositor, so input-frame ownership no longer scales with
   layer count. The immutable output contract and established bytes are unchanged.
6. **Large/high-layer stress evidence was weak — fixed in bounded scope.** Tests render
   the 16-layer maximum at 960×540 while observing at most one earlier input buffer
   alive at the next layer boundary. The manual probe supports 16 layers at arbitrary
   requested viewports. Existing 16-layer and 4,096-particle caps remain justified;
   no arbitrary hardware viewport cap was introduced. One local 1920×1080,
   16-layer characterization rendered 36 frames in 15.10 seconds. Each RGBA plane is
   8,294,400 bytes; observed process peak working set was 54,050,816 bytes and peak
   private bytes was 547,000,320 bytes. Post-warmup start/end deltas were +4,452,352
   working-set bytes and +4,747,264 private bytes. This short run characterizes cost;
   it is not presented as longevity or leak evidence.
7. **Artifact checks favored v1 behavior — fixed.** Required wheel inventory and the
   CPython artifact matrix now cover scene modules, `--list-scenes`, strict scene TOML,
   deterministic custom-scene construction, and non-interactive rendering. A rebuilt
   release candidate passed the complete offline artifact and installer matrix on
   CPython 3.11-3.14.
8. **Metadata remains `1.0.0` — verified, not changed.** Repository policy defines no
   next public version. Selecting one is a release-policy decision; publishing remains
   blocked until version metadata, filenames, and contracts are updated consistently.
9. **The scene engine arrived in one large commit — reviewed.** The ordered immutable
   scene boundary, structural layer protocol, explicit time/context, RNG derivation,
   resize reconstruction, config validation, terminal separation, and lifecycle
   ownership remain coherent. Concrete memory and extreme-time defects were fixed;
   no large redesign was justified.
10. **Completion evidence overstated process memory — fixed.** Phase 10 now identifies
    its recorded delta as terminal-emulator evidence. Current hardening claims separate
    source, installed-artifact, live-terminal, and manual longevity evidence.

## Evidence boundaries and residual risk

- The repeatable source gate excludes only tests marked `wezterm_live`; those need an
  interactive disposable WezTerm pane.
- The process probe measures working set and private bytes of the actual Python
  renderer. It does not prove that all native allocations are leak-free, and allocator
  high-water retention can look like growth.
- Full-viewport immutable rendering still necessarily allocates buffers proportional
  to pixel area. Layer and particle amplification are capped, but core `Viewport`
  remains an explicit caller-provided value so offline rendering is not tied to an
  arbitrary monitor-size policy.
- Scene configuration version 1 intentionally requires one text layer under ADR 0009.
  The core `Scene` itself has no text requirement; a future text-free user format must
  use a new configuration version rather than changing version 1 semantics.
- The public post-v1 release version remains undecided. Do not publish or tag until it
  is chosen.
