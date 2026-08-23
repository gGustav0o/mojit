from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SOURCE_ROOT = PROJECT_ROOT / "src" / "mojit"
CORE_ROOT = SOURCE_ROOT / "core"
CONFIG_ROOT = SOURCE_ROOT / "config"
APPLICATION_REQUEST = SOURCE_ROOT / "application" / "request.py"
APPLICATION_ROOT = SOURCE_ROOT / "application"
EFFECTS_ROOT = SOURCE_ROOT / "effects"
WEZTERM_ROOT = SOURCE_ROOT / "adapters" / "wezterm"
WEZTERM_BACKEND = WEZTERM_ROOT / "backend.py"
WEZTERM_VIEWPORT = WEZTERM_ROOT / "viewport.py"
FORBIDDEN_CORE_PREFIXES = ("mojit.application", "mojit.adapters", "mojit.config", "mojit.cli")
FORBIDDEN_CONFIG_PREFIXES = ("mojit.application", "mojit.adapters", "mojit.effects", "mojit.cli")
FORBIDDEN_REQUEST_PREFIXES = ("mojit.adapters", "mojit.config", "mojit.cli")
FORBIDDEN_APPLICATION_PREFIXES = ("mojit.adapters", "mojit.config", "mojit.cli")
FORBIDDEN_APPLICATION_MODULES = {"os", "pathlib", "subprocess", "time"}
FORBIDDEN_EFFECT_PREFIXES = (
    "mojit.application",
    "mojit.adapters",
    "mojit.config",
    "mojit.cli",
)
FORBIDDEN_EFFECT_MODULES = {"os", "pathlib", "random", "subprocess", "time"}
FORBIDDEN_WEZTERM_PREFIXES = ("mojit.application", "mojit.config", "mojit.effects", "mojit.cli")


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


def test_config_does_not_import_outer_project_layers() -> None:
    violations: list[str] = []
    for path in CONFIG_ROOT.rglob("*.py"):
        for imported in _imports(path):
            if imported.startswith(FORBIDDEN_CONFIG_PREFIXES):
                violations.append(f"{path.relative_to(PROJECT_ROOT)} -> {imported}")

    assert violations == []


def test_prepared_request_has_no_shell_dependencies() -> None:
    violations = [
        imported
        for imported in _imports(APPLICATION_REQUEST)
        if imported.startswith(FORBIDDEN_REQUEST_PREFIXES)
    ]
    assert violations == []


def test_application_depends_only_on_core_effects_and_stdlib_without_shell_io() -> None:
    violations: list[str] = []
    for path in APPLICATION_ROOT.rglob("*.py"):
        for imported in _imports(path):
            top_level = imported.split(".")[0]
            if (
                imported.startswith(FORBIDDEN_APPLICATION_PREFIXES)
                or top_level in FORBIDDEN_APPLICATION_MODULES
            ):
                violations.append(f"{path.relative_to(PROJECT_ROOT)} -> {imported}")

    assert violations == []


def test_effects_do_not_import_shell_layers_or_side_effect_modules() -> None:
    violations: list[str] = []
    for path in EFFECTS_ROOT.rglob("*.py"):
        for imported in _imports(path):
            top_level = imported.split(".")[0]
            if (
                imported.startswith(FORBIDDEN_EFFECT_PREFIXES)
                or top_level in FORBIDDEN_EFFECT_MODULES
            ):
                violations.append(f"{path.relative_to(PROJECT_ROOT)} -> {imported}")

    assert violations == []


def test_concrete_effects_do_not_import_registry() -> None:
    violations: list[str] = []
    for path in EFFECTS_ROOT.glob("*.py"):
        if path.name == "registry.py":
            continue
        if "mojit.effects.registry" in _imports(path):
            violations.append(str(path.relative_to(PROJECT_ROOT)))

    assert violations == []


def test_wezterm_adapter_does_not_import_application_or_shell_composition() -> None:
    violations: list[str] = []
    for path in WEZTERM_ROOT.rglob("*.py"):
        for imported in _imports(path):
            if imported.startswith(FORBIDDEN_WEZTERM_PREFIXES):
                violations.append(f"{path.relative_to(PROJECT_ROOT)} -> {imported}")

    assert violations == []


def test_subprocess_access_is_isolated_to_viewport_adapter() -> None:
    violations: list[str] = []
    for path in WEZTERM_ROOT.rglob("*.py"):
        if path == WEZTERM_VIEWPORT:
            continue
        if "subprocess" in _imports(path):
            violations.append(str(path.relative_to(PROJECT_ROOT)))

    assert violations == []


def test_wezterm_backend_is_application_port_agnostic() -> None:
    assert not any(
        imported.startswith("mojit.application") for imported in _imports(WEZTERM_BACKEND)
    )
