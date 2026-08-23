from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SOURCE_ROOT = PROJECT_ROOT / "src" / "mojit"
CORE_ROOT = SOURCE_ROOT / "core"
FORBIDDEN_CORE_PREFIXES = ("mojit.application", "mojit.adapters", "mojit.config", "mojit.cli")


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.append(node.module)
    return imported


def test_core_does_not_import_outer_project_layers() -> None:
    violations: list[str] = []
    for path in CORE_ROOT.rglob("*.py"):
        for imported in _imports(path):
            if imported.startswith(FORBIDDEN_CORE_PREFIXES):
                violations.append(f"{path.relative_to(PROJECT_ROOT)} -> {imported}")

    assert violations == []


def test_production_package_never_imports_spikes() -> None:
    violations: list[str] = []
    for path in SOURCE_ROOT.rglob("*.py"):
        for imported in _imports(path):
            if imported == "spikes" or imported.startswith("spikes."):
                violations.append(f"{path.relative_to(PROJECT_ROOT)} -> {imported}")

    assert violations == []
