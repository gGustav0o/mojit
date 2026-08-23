# Phase 2 report

Phase 2 is complete.

Implemented:

- frozen partial and resolved configuration models with documented limits;
- strict pure TOML decoding and closed root-level schema;
- bounded UTF-8 config discovery at `--config` or `%APPDATA%/mojit/config.toml`;
- explicit field-by-field `CLI > file > defaults` resolution;
- source-relative font paths;
- all v1 CLI flags and isolated list command mode;
- positional/UTF-8 stdin precedence and single-line text validation;
- immutable `PreparedRun` without paths, streams, or adapter objects;
- font loading and public Raqm/FriBiDi preflight before terminal access;
- stable user/unexpected error exit categories with debug-only tracebacks.

Verification:

```text
pytest:                         220 passed
Phase 2 focused coverage:      94.85% (required >= 90%)
ruff check:                    passed
ruff format --check:           passed
```

No effect execution, terminal query/state mutation, frame rendering, or animation
loop was introduced. The next boundary is Phase 3: pure compositor primitives and
the first deterministic effect set.
