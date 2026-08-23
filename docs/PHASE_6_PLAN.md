# Phase 6: reproducible Windows distribution

Status: complete. Evidence: [PHASE_6_REPORT.md](PHASE_6_REPORT.md).

## Goal

Turn the source-complete v1 into one reproducible, installable Windows x64 release
candidate whose vertical shaping does not depend on an ambient FriBiDi DLL.

Phase 6 starts from the accepted Phase 5 source runtime. It ends with a clean-machine
installation from built artifacts, verified horizontal and vertical rendering in
WezTerm, complete native-dependency provenance, and release evidence. Rendering,
effects, scheduling, terminal transport, and user configuration remain unchanged.

## Release contract

The recommended v1 distribution contract is:

```text
platform:          Windows 11 x64
terminal:          user-installed WezTerm
python:            user-installed CPython 3.11-3.14 x64
primary artifact:  py3-none-win_amd64 wheel
offline bundle:    wheelhouse ZIP with exact dependency wheels
native runtime:    bundled dynamic libfribidi-0.dll
font:              not bundled
installation:      isolated venv or pipx
```

Release deliverables:

```text
mojit-{version}-py3-none-win_amd64.whl
mojit-{version}-windows-x64-wheelhouse.zip
SHA256SUMS.txt
THIRD_PARTY_NOTICES.md
FriBiDi source archive + build/provenance manifest
PHASE_6_REPORT.md
```

The platform tag is mandatory: a wheel containing a Windows x64 DLL must never be
published as `py3-none-any`.

## Frozen phase-entry decisions

The project license is MIT with copyright `2026 mojit contributors`. The release
candidate version is `1.0.0`; supported interpreters are CPython 3.11-3.14 x64.
Runtime pins are NumPy 2.4.6, Pillow 12.3.0, and FriBiDi 1.0.16. Artifacts are retained
under ignored `dist/release/` only. Publication, signing, credentials, repository URL,
and remote retention remain explicitly deferred.

## Scope

Phase 6 includes:

- a pinned application-controlled FriBiDi Windows x64 DLL;
- source checksum, binary checksum, build recipe, dependency inspection, and license;
- a stdlib-only native-runtime bootstrap executed before Pillow's native text stack;
- process-lifetime retention of the `os.add_dll_directory()` handle;
- platform-correct wheel metadata and explicit package-data inclusion;
- exact release dependency constraints and an offline wheelhouse;
- artifact content, metadata, install, uninstall, and tamper tests;
- clean-Windows tests with ambient third-party DLL directories removed;
- installed-command WezTerm acceptance for horizontal, vertical, resize, and cleanup;
- deterministic release scripts, checksum generation, and release documentation.

## Non-goals

Do not add in this phase:

- changes to effects, typography semantics, layout, animation, or terminal protocol;
- bundled Python, WezTerm, or CJK fonts;
- general font discovery or a manual vertical-layout fallback;
- support for Windows ARM64, Windows 10, Linux, macOS, or other terminals;
- a standalone EXE, MSI/MSIX installer, GUI installer, or auto-updater;
- PyInstaller/Nuitka or a second application composition root;
- static linking of FriBiDi into Pillow or another binary;
- runtime downloads, self-update, registry writes, or global `PATH` mutation;
- public upload, code signing, or release credentials without explicit authorization;
- dependency upgrades unrelated to the verified artifact matrix.

The wheel plus offline wheelhouse is the only v1 artifact family. A standalone
installer can be evaluated later from actual distribution requirements.

## Fixed architecture

```text
installed console script / python -m mojit
                    │
                    ▼
             bootstrap.py
                    │
                    ├── locate packaged _native/win_amd64
                    ├── verify required files exist
                    ├── os.add_dll_directory(exact directory)
                    └── retain handle for process lifetime
                    │
                    ▼
                 cli.py
                    │
                    ▼
        existing Phase 5 application/runtime
```

Dependency rules:

- `core`, `effects`, `application`, and WezTerm adapters remain packaging-agnostic;
- only the native bootstrap knows the bundled DLL path;
- bootstrap imports stdlib and native-runtime support only before activation;
- bootstrap imports `cli` only after successful DLL-directory registration;
- `cli` remains the application composition root and exit-policy owner;
- build scripts never become importable production modules;
- package resources contain binaries/notices, not rendering or configuration policy;
- neither `PATH` nor the current working directory participates in DLL selection.

Add dependency tests that make the import order and layer restrictions executable.

## Native runtime contract

The package contains a replaceable dynamic `libfribidi-0.dll` under one exact
architecture-specific directory. Bootstrap behavior:

1. resolve the directory relative to the installed `mojit` package, never CWD;
2. require the expected DLL and packaged provenance metadata;
3. exclude legacy `PATH` lookup, register the package directory, and load FriBiDi by
   absolute path before importing `mojit.cli` or Pillow;
4. retain the directory and library handles in module-owned process-lifetime state;
5. call activation at most once and return the same state on repeated calls;
6. map missing/inaccessible runtime files to one actionable pre-terminal exit `2`;
7. never scan `PATH`, copy a system DLL, download at runtime, or mutate global `PATH`.

Checksums are enforced during build and artifact verification. Do not enforce a
hardcoded runtime binary checksum: the LGPL library remains a separate replaceable
DLL, while the subsequent Raqm capability check verifies compatibility.

The native manifest records at least:

```text
name
upstream project and source URL
version and source tag/commit
source archive SHA-256
build recipe and flags
compiler/tool versions
target architecture
output DLL name and SHA-256
direct binary dependencies
license identifier and packaged license path
```

The build must inspect DLL dependencies and reject undeclared non-system runtime
dependencies. Ambient copies from ImageMagick, Tesseract, Git, GTK, or other software
are never valid inputs.

## Artifact contract

The wheel must contain only production Python packages, the selected DLL, native
manifest, and required license/notice files. It must exclude tests, spikes, caches,
local configuration, build logs, and source-control metadata.

Required metadata:

- non-placeholder version;
- `Requires-Python` consistent with the verified matrix;
- exact or release-constrained NumPy/Pillow dependencies;
- Windows x64 platform tag;
- `mojit` console entry pointing to the bootstrap;
- project license expression and license files after owner approval;
- complete third-party notices.

The wheelhouse ZIP contains the mojit wheel and exact compatible dependency wheels.
Installation acceptance uses only this directory with `--no-index`; therefore no
network, global package, or user-site dependency can mask an incomplete release.

Every release file receives SHA-256 in `SHA256SUMS.txt`. The verification script
must reconstruct and compare the manifest before installation.

## Clean-environment contract

The release gate uses a fresh Windows VM or hosted runner with:

- an explicit non-floating Windows image where CI permits it;
- a newly installed supported CPython;
- `PYTHONNOUSERSITE=1`;
- a new venv for each matrix cell;
- a sanitized child `PATH` without ImageMagick, Tesseract, Git/MSYS, GTK, or other
  FriBiDi providers;
- install only from the generated wheelhouse;
- Japanese Supplemental Fonts provisioned for the default-font case;
- an explicit user-supplied CJK font case kept separate from the default-font case;
- a pinned WezTerm version for installed live acceptance.

The clean test proves the loaded FriBiDi module path belongs to the installed mojit
package. Add a hostile-shadow case with an incompatible same-named DLL earlier on
`PATH`; bundled resolution must still win. Removing the packaged DLL must fail before
terminal mutation and must not fall back to ambient software.

## Work sequence

### P6.0 — Freeze release and legal contract

1. Record the chosen project license, copyright holder, initial version, supported
   Python minors, and local artifact-retention policy.
2. Confirm the canonical wheel/wheelhouse contract and `win_amd64` scope.
3. Pin runtime and release-tool versions in a release constraints file.
4. Record exact clean-image and WezTerm acceptance versions.
5. Update `SPEC.md` and ADR 0003 only where the finalized distribution contract adds
   durable product constraints.

Exit condition: artifact identity, support matrix, legal inputs, and promotion rules
contain no placeholders or implicit assumptions.

### P6.1 — Reproduce and vendor FriBiDi

1. Select one stable upstream FriBiDi source release after reviewing Pillow ABI
   compatibility; do not copy the ambient machine DLL.
2. Download by immutable URL, verify the pinned source SHA-256, and build x64 from the
   recorded recipe.
3. Inspect architecture, exports, and direct dependencies.
4. run horizontal/vertical shaping against the built DLL under a sanitized `PATH`.
5. Add the DLL, upstream license, exact source archive, manifest, and reproduction
   script to the distribution inputs.

Exit condition: another clean builder can reproduce or independently verify the
vendored DLL without relying on the reference workstation.

### P6.2 — Implement early native bootstrap

1. Add a narrow native-runtime loader and package-relative resource layout.
2. Activate the exact DLL directory before importing `cli`/Pillow.
3. Retain the DLL-directory handle and make activation idempotent.
4. Route both the console script and `python -m mojit` through the same bootstrap.
5. Add import-order, missing-resource, repeated-activation, wrong-platform, and
   no-`PATH`-mutation tests.

Exit condition: a sanitized subprocess imports the installed command with Raqm
available solely through the packaged DLL, before any terminal operation.

### P6.3 — Build platform-correct artifacts

1. Complete project metadata and configure explicit binary/package data.
2. Produce `py3-none-win_amd64`, rejecting `*-any.whl` as a build failure.
3. Build an exact offline wheelhouse for every supported Python matrix cell or prove
   one wheelhouse is compatible with the complete matrix.
4. Generate notices, provenance, source archive, and SHA-256 manifests.
5. Build twice from clean directories and compare artifact inventories and hashes;
   explain any unavoidable non-byte-identical metadata.

Exit condition: artifact generation is scripted, non-interactive, and independent of
the developer environment.

### P6.4 — Artifact inspection and offline installation gate

1. Inspect wheel filename, `WHEEL`, `METADATA`, entry points, licenses, and exact file
   allowlist without importing it.
2. Reject path traversal, duplicate files, missing hashes, undeclared binaries, debug
   artifacts, and unexpected executable content.
3. Install into a new venv with `--no-index --find-links` and user site disabled.
4. Verify `mojit --help`, `--list-effects`, positional/piped UTF-8, exit codes, and
   uninstall/reinstall behavior through the installed command.
5. Verify missing/tampered native payload errors occur before terminal bytes.

Exit condition: tests exercise only built artifacts, never the source tree or editable
installation.

### P6.5 — Clean-Windows native and typography matrix

1. Run the supported CPython x64 matrix on clean Windows.
2. Assert no ambient FriBiDi provider is visible and record the actually loaded DLL
   path/version/hash.
3. Run deterministic horizontal and vertical typography references with the packaged
   native runtime.
4. Test default font present, default font absent, and explicit CJK font paths.
5. Repeat with hostile `PATH`, missing DLL, wrong architecture, and incompatible DLL.

Exit condition: vertical shaping succeeds only from the packaged native runtime and
all invalid installations fail before terminal mutation.

### P6.6 — Installed WezTerm acceptance

1. Install the wheelhouse into a fresh environment on the reference Windows/WezTerm
   machine or clean GUI-capable VM.
2. Run horizontal and vertical CJK through the installed `mojit` command.
3. Exercise resize, piped input, real `Ctrl+C`, injected failure harness, and repeated
   cleanup.
4. Re-run the five-minute structured workload from the installed artifact.
5. Record versions, commands, frame/latency/byte/resize metrics, process working-set
   delta, loaded DLL identity, and final terminal state.

Exit condition: installed behavior reproduces Phase 5 source-checkout evidence and
loads no ambient native dependency.

### P6.7 — Release automation and report

1. Add one local PowerShell release entry point; CI is a thin invocation of the same
   scripts rather than a second build implementation.
2. Pin CI actions/tools, use least permissions, and keep publication/signing separate
   from untrusted pull-request builds.
3. Run source tests, coverage, lint, format, compile, native verification, artifact
   inspection, clean install, and installed live gates.
4. Write `docs/PHASE_6_REPORT.md` with artifact hashes and all clean-machine evidence.
5. Update README with exact install, upgrade, uninstall, prerequisites, verification,
   third-party notices, and recovery instructions.

Exit condition: one reviewed command creates a complete release-candidate set and
one independent command verifies it from hashes through installed live behavior.

## Planned layout

```text
src/mojit/bootstrap.py
src/mojit/native_runtime.py
src/mojit/_native/win_amd64/libfribidi-0.dll
src/mojit/_native/manifest.toml
src/mojit/_native/licenses/COPYING-LGPL-2.1-or-later.txt

vendor/fribidi/source/<pinned-source-archive>
vendor/fribidi/README.md
tools/release/build_fribidi.ps1
tools/release/build_artifacts.ps1
tools/release/verify_artifacts.ps1
tools/release/artifact_contract.py
tools/release/installed_probe.py
tools/release/installed_interrupt_controller.py
tools/release/run_installed_live.ps1
constraints/release-win-amd64.txt

tests/unit/test_native_runtime.py
tests/unit/test_bootstrap.py
tests/release/test_wheel_contract.py

THIRD_PARTY_NOTICES.md
docs/PHASE_6_REPORT.md
```

Generated `build/`, `dist/`, wheelhouse, and acceptance logs remain ignored. Pinned
source/provenance/license inputs are versioned.

## Required gates

Source gate:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check src tests tools
.\.venv\Scripts\python.exe -m ruff format --check src tests tools
.\.venv\Scripts\python.exe -m compileall -q src tests
```

Release gate, exposed through stable scripts rather than copied command sequences:

```powershell
.\tools\release\build_artifacts.ps1
.\tools\release\verify_artifacts.ps1
```

The verification script must fail closed on a dirty staging directory, checksum
mismatch, wrong platform tag, missing notice/source, network-dependent install,
ambient FriBiDi load, skipped matrix cell, or failed installed live acceptance.

## Phase gate

Phase 6 is complete only when:

- owner-approved project license and non-placeholder version are recorded;
- the canonical artifact is a valid Windows x64 wheel, never a universal wheel;
- the wheel contains bundled FriBiDi and the offline wheelhouse contains every
  declared Python package dependency;
- FriBiDi source, build recipe, hashes, binary dependencies, and notices are complete;
- bootstrap registers only the packaged DLL directory before Pillow import and keeps
  the handle alive;
- the release never scans or mutates `PATH` and never copies an ambient DLL;
- clean, hostile, missing, incompatible, and wrong-architecture cases behave as
  specified before terminal mutation;
- all supported Python matrix cells install only from built artifacts and pass;
- default-font and explicit-font paths have separate clean evidence;
- installed horizontal/vertical rendering, resize, interrupt, and cleanup pass;
- the installed five-minute workload has recorded bounded-resource evidence;
- artifact contents and SHA-256 manifests are independently verified;
- source and release quality gates pass without skips;
- README and Phase 6 report reproduce installation and verification exactly;
- artifacts remain local; public publication/signing requires a separate phase and
  explicit authorization.

## Implementation increments

Keep commits independently reviewable:

1. release/legal contract and pinned provenance inputs;
2. reproducible FriBiDi build and native verification;
3. early bootstrap and import-boundary tests;
4. platform wheel and offline wheelhouse construction;
5. artifact inspection and clean-install matrix;
6. installed WezTerm acceptance, automation, documentation, and report.

## Optimal execution order

```text
P6.0 release contract
          │
          ▼
P6.1 FriBiDi provenance/build
          │
          ▼
P6.2 early bootstrap
          │
          ▼
P6.3 artifact construction
          │
          ▼
P6.4 offline artifact gate
          │
          ▼
P6.5 clean-Windows matrix
          │
          ▼
P6.6 installed WezTerm acceptance
          │
          ▼
P6.7 automation/report
```

Do not start installed acceptance before the artifact passes offline inspection. Do
not automate publication before clean-machine evidence is complete.
