# Phase 2: configuration and input boundary

Status: complete. The verified outcome is recorded in
[PHASE_2_REPORT.md](PHASE_2_REPORT.md).

## Goal

Transform explicit `argv`, an optional TOML document, process environment, current
directory, and positional or piped Unicode text into one fully validated immutable
`PreparedRun` before any terminal state is changed.

Phase 2 owns user-input policy. It does not render frames, enumerate implemented
effects, query WezTerm, or enter the terminal alternate screen.

## Scope

Phase 2 includes:

- immutable partial and resolved configuration models;
- strict TOML decoding and config-file discovery;
- pure `CLI > config file > defaults` resolution;
- CLI syntax and command-mode parsing;
- positional-text and UTF-8 stdin resolution;
- font-path resolution and Phase 1 font-resource loading;
- explicit Raqm/FriBiDi preflight;
- assembly of an immutable application-facing `PreparedRun`;
- user-facing error categories and exit-code mapping;
- unit and non-terminal integration tests.

## Non-goals

Do not implement in this phase:

- effects, compositor, or effect registry execution;
- `--list-effects` output beyond parsing the command intent;
- `TextMask` caching;
- frame scheduling or animation loop;
- WezTerm viewport queries, graphics output, or terminal state;
- FriBiDi binary packaging;
- general font discovery;
- interactive prompts;
- environment-variable overrides for ordinary rendering options.

## Fixed defaults and limits

The production defaults are:

```text
effect:       neon
orientation:  horizontal
font:         C:/Windows/Fonts/YuGothB.ttc
fps:          30
margin:       0.08
seed:         0
debug:        false
```

Validation limits:

```text
fps:                 1..60
margin:              0 <= margin < 0.5
seed:                signed 64-bit integer
text length:         1..4096 Unicode code points
config file size:    at most 1 MiB
effect identifier:   [a-z][a-z0-9_-]*
```

The 60 FPS limit reflects the Phase 0 transport boundary: 60 is accepted as
best-effort, not guaranteed. No value is silently clamped or coerced.

## Data flow and ownership

```text
argv
  ↓ parse_cli(argv)
ParsedCli
  ├── command mode
  ├── optional positional text
  ├── optional config path
  └── ConfigOverrides

environment + config path
  ↓ config-file adapter
optional ConfigDocument
  ↓ strict TOML parser
ConfigOverrides

defaults + file overrides + CLI overrides
  ↓ pure resolve_config(...)
ResolvedConfig

positional text OR piped UTF-8
  ↓ input shell + pure text validation
ValidatedText

ResolvedConfig.font
  ↓ font-resource adapter + shaping preflight
font bytes + SHA-256

ValidatedText + resolved values + font identity/data
  ↓ composition root mapping
PreparedRun
```

`PreparedRun` contains narrow runtime values, not `argparse.Namespace`, TOML
dictionaries, paths to unread files, open streams, or adapter objects. Rendering core
must never receive `ResolvedConfig` directly.

## Configuration models

Implement in `src/mojit/config/models.py`:

- `ConfigOverrides`: all configurable fields optional;
- `ResolvedConfig`: every runtime field present and validated;
- constants for configuration defaults and validation limits.

`CommandMode` and `ParsedCli` remain private CLI-boundary models in `src/mojit/cli.py`;
they are not configuration concepts. Text and config-file size limits live beside
the code that enforces them.

Configurable TOML fields:

```text
effect
orientation
font
fps
margin
seed
```

`debug`, `config`, and `list-effects` are CLI concerns and are not TOML keys.
`ResolvedConfig.debug` is `false` unless `--debug` is present.

Models use frozen, slotted dataclasses. Optional means “source did not provide a
value”; falsey values such as `0` are never treated as missing.

## TOML contract

`src/mojit/config/toml.py` performs pure decoding from UTF-8 text or bytes into
`ConfigOverrides`. It does not open paths.

Rules:

- only root-level keys listed above are accepted;
- unknown keys and nested tables are errors;
- TOML types are exact: booleans are not integers;
- strings are not converted to numbers or enums;
- `orientation` accepts only `horizontal` or `vertical`;
- empty effect/font strings are errors;
- syntax failures are mapped to a stable project exception without leaking a
  traceback in normal mode.

The file adapter is `src/mojit/adapters/config_file.py` and owns filesystem access.
It applies the 1 MiB limit and strict UTF-8 decoding.

Config discovery:

1. explicit `--config PATH`;
2. `%APPDATA%/mojit/config.toml` when `APPDATA` exists;
3. no config document.

An explicitly selected missing/unreadable file is an error. An absent implicit
default file is normal. `--config -` is rejected because stdin is reserved for text.

Relative paths have stable bases:

- `font` from CLI is relative to the invocation current directory;
- `font` from TOML is relative to the config file directory;
- the built-in font path is already absolute.

Normalize to an absolute `Path` without requiring existence during pure resolution;
the font adapter performs existence and content validation during preflight.

## Configuration precedence

Implement `src/mojit/config/resolve.py` as a pure, explicit field-by-field resolver:

```text
CLI override
↓ when absent
config-file override
↓ when absent
built-in default
```

Do not merge `__dict__`, reflect over dataclass fields, or use truthiness-based
fallbacks. Tests must independently prove precedence for every field.

Orientation is one tri-state CLI override:

```text
--vertical    -> vertical
--horizontal  -> horizontal
neither       -> no CLI override
```

Therefore `--horizontal` explicitly overrides `orientation = "vertical"` in TOML.

## CLI contract

Use stdlib `argparse` in `src/mojit/cli.py`. Keep parsing separate from process I/O:

```python
parse_cli(argv: Sequence[str]) -> ParsedCli
main(argv: Sequence[str] | None = None) -> int
```

Rules:

- parser construction and parsing never read global `sys.argv` in tests;
- `--vertical` and `--horizontal` are mutually exclusive;
- the positional text is optional at parse time because stdin may supply it;
- `--list-effects` selects a separate command mode;
- list mode rejects positional text, `--config`, and rendering overrides, and never
  reads config, stdin, or font resources;
- argparse exits and errors are mapped to `CliUsageError` for testability;
- `--help` retains conventional successful behavior;
- user errors exit with code `2`;
- unexpected failures exit with code `1`;
- `--debug` controls traceback exposure, not validation behavior.

Phase 2 parses every v1 flag from `SPEC.md`. Execution of `LIST_EFFECTS` is deferred
until the effect registry exists.

## Text-input contract

Split I/O from policy:

- the shell decides whether stdin is a TTY and reads it only when needed;
- a pure validator normalizes and validates the resulting string.

Rules:

1. positional text wins and stdin is not touched;
2. without positional text, a TTY stdin fails immediately instead of blocking;
3. piped stdin is decoded as strict UTF-8 on Windows;
4. remove exactly one terminal `\r\n` or `\n` added by the pipeline;
5. preserve all other Unicode and spaces exactly;
6. reject empty/whitespace-only text, NUL, internal CR/LF, and more than 4096 code
   points;
7. report invalid UTF-8 as an input error, not a Python codec traceback.

Tests use streams that fail if read to prove positional precedence.

## Startup preflight

Before producing `PreparedRun`:

1. resolve the absolute font path using the source-specific base directory;
2. call the Phase 1 font-resource adapter;
3. verify Pillow Raqm/FriBiDi capability through a public typography preflight;
4. retain only immutable font bytes and SHA-256 identity;
5. do not query or mutate the terminal.

Define `PreparedRun` in `src/mojit/application/request.py` with:

```text
text
effect_id
orientation
font_data
font_fingerprint
fps
margin
seed
debug
```

It may depend on core value types, but not on CLI, adapters, TOML, environment, or
terminal types. The composition root maps resolved configuration and adapter output
into it explicitly.

## Error model

Use narrow errors with one user action per category:

```text
CliUsageError
ConfigFileError
ConfigSyntaxError
ConfigValidationError
InputTextError
FontResourceError
ShapingUnavailableError
```

Normal output contains a concise message and the relevant option/path/key. It must
not expose internal stack traces. Debug mode preserves exception chaining and prints
the traceback at the outermost boundary.

## Work sequence

### P2.0 — Freeze user-visible contracts

1. Add the defaults, limits, default config location, single-line text rule, and exit
   codes to `SPEC.md`.
2. Add table-driven tests for every accepted and rejected boundary value.
3. Confirm that Phase 1 models remain unchanged unless a real missing capability is
   exposed.

Exit condition: implementation cannot invent config behavior implicitly.

### P2.1 — Models and pure validation

Implement `ConfigOverrides`, `ResolvedConfig`, configuration constants, and reusable
strict validators. Keep `ParsedCli` and command mode at the CLI boundary. Do not
import argparse, TOML, filesystem, or streams into configuration models.

Exit condition: all valid states are representable and invalid resolved states are
unconstructable.

### P2.2 — Strict TOML decoding

Implement syntax mapping, exact key/type validation, orientation conversion, and
unknown-key rejection in `config.toml`.

Exit condition: arbitrary dictionaries cannot cross the parser boundary.

### P2.3 — Pure precedence resolution

Implement explicit CLI/file/default selection and source-aware font-path resolution.
Test all fields independently, including falsey `seed = 0` and explicit horizontal
orientation.

Exit condition: one deterministic `ResolvedConfig` is produced without I/O.

### P2.4 — CLI parsing

Implement all v1 flags, mutual exclusion, command-mode constraints, stable errors,
and explicit `argv` parsing.

Exit condition: parser tests require no monkeypatching of process globals.

### P2.5 — Config and stdin shells

Implement bounded config-file reads, discovery policy, stdin TTY detection, strict
UTF-8 handling, terminal-newline removal, and pure text validation.

Exit condition: positional input cannot consume stdin, and invalid input cannot
reach font loading.

### P2.6 — Font and shaping preflight

Expose the smallest public Phase 1 capability check, load the resolved font, and map
all dependency failures before terminal work.

Exit condition: an invalid font or missing Raqm/FriBiDi produces one actionable error
without emitting escape sequences.

### P2.7 — Prepared request assembly

Implement explicit mapping to `PreparedRun`. Do not pass `ResolvedConfig` into core
typography or store adapter instances in application state.

Exit condition: later phases need no knowledge of argv, TOML, paths, or stdin.

### P2.8 — Integrated non-terminal gate

Exercise:

1. positional text with defaults;
2. piped Japanese text;
3. explicit TOML config;
4. CLI overrides for every config field;
5. `--horizontal` over vertical config;
6. implicit missing config;
7. explicit missing/malformed config;
8. invalid UTF-8 and empty input;
9. missing/invalid font and unavailable shaping;
10. list mode without stdin/config/font access.

Every scenario asserts that stdout contains no terminal control sequence and no
WezTerm subprocess was invoked.

## Test layout

```text
tests/unit/config/test_models.py
tests/unit/config/test_toml.py
tests/unit/config/test_resolve.py
tests/unit/application/test_input_text.py
tests/unit/application/test_request.py
tests/unit/adapters/test_config_file.py
tests/unit/test_cli.py
tests/integration/test_prepare_run.py
```

Required checks:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m pytest --cov=mojit.config --cov=mojit.cli `
  --cov=mojit.application.request --cov=mojit.application.input_text `
  --cov=mojit.adapters.config_file --cov-fail-under=90
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m ruff format --check src tests
```

System-independent unit tests never skip. The real-font preflight integration may
skip only with a precise reference-environment reason.

## Implementation increments

Keep increments independently reviewable:

1. SPEC defaults and config models;
2. TOML parser and config-file adapter;
3. pure precedence resolver;
4. CLI parser;
5. stdin/text resolver;
6. preflight and `PreparedRun`;
7. integrated gate and report.

Do not begin terminal or effect work to make an integration test pass.

## Phase gate

Phase 2 is complete only when:

- every v1 CLI flag parses with documented semantics;
- every resolved field obeys `CLI > file > defaults`;
- positional text provably prevents stdin reads;
- piped Japanese UTF-8 survives unchanged except one terminal newline;
- config parsing is strict, bounded, and rejects unknown keys;
- relative font paths use the documented source-specific base;
- font and shaping failures occur before terminal mutation;
- `PreparedRun` contains no CLI, TOML, path, stream, or adapter object;
- list mode performs no unrelated I/O;
- unit, integration, coverage, lint, format, dependency, and documentation checks
  pass;
- no Phase 3+ runtime behavior has leaked into the implementation.

## Follow-up boundary

After this gate, Phase 3 should implement the pure compositor primitives and first
deterministic effect set. Mutable mask caching, scheduler, animation orchestration,
and the production WezTerm backend remain later phases.
