from __future__ import annotations

from pathlib import Path

import pytest

from mojit.adapters.config_file import (
    MAX_CONFIG_BYTES,
    ConfigDocument,
    ConfigFileError,
    load_config_document,
)


def test_no_appdata_means_no_implicit_config(tmp_path: Path) -> None:
    assert load_config_document(None, environ={}, cwd=tmp_path) is None


def test_absent_implicit_config_is_normal(tmp_path: Path) -> None:
    assert load_config_document(None, environ={"APPDATA": str(tmp_path)}, cwd=tmp_path) is None


def test_implicit_config_is_discovered_and_decoded(tmp_path: Path) -> None:
    path = tmp_path / "mojit" / "config.toml"
    path.parent.mkdir()
    path.write_bytes(b'effect = "neon"\n')

    document = load_config_document(None, environ={"APPDATA": str(tmp_path)}, cwd=tmp_path)

    assert document is not None
    assert document.source == path.resolve()
    assert document.text == 'effect = "neon"\n'


def test_explicit_relative_config_uses_invocation_directory(tmp_path: Path) -> None:
    path = tmp_path / "settings.toml"
    path.write_text("fps = 60\n", encoding="utf-8")

    document = load_config_document("settings.toml", environ={}, cwd=tmp_path)

    assert document is not None
    assert document.source == path.resolve()


def test_explicit_missing_config_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigFileError, match="does not exist"):
        load_config_document("missing.toml", environ={}, cwd=tmp_path)


def test_directory_is_not_a_config_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigFileError, match="not a file"):
        load_config_document(tmp_path, environ={}, cwd=tmp_path)


def test_oversized_config_is_rejected_before_decoding(tmp_path: Path) -> None:
    path = tmp_path / "large.toml"
    path.write_bytes(b"x" * (MAX_CONFIG_BYTES + 1))
    with pytest.raises(ConfigFileError, match="1 MiB"):
        load_config_document(path, environ={}, cwd=tmp_path)


def test_config_at_exact_size_limit_is_accepted(tmp_path: Path) -> None:
    path = tmp_path / "limit.toml"
    path.write_bytes(b" " * MAX_CONFIG_BYTES)

    document = load_config_document(path, environ={}, cwd=tmp_path)

    assert document is not None
    assert len(document.text) == MAX_CONFIG_BYTES


def test_invalid_utf8_config_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "invalid.toml"
    path.write_bytes(b"\xff")
    with pytest.raises(ConfigFileError, match="UTF-8"):
        load_config_document(path, environ={}, cwd=tmp_path)


def test_dash_is_reserved_for_text_stdin(tmp_path: Path) -> None:
    with pytest.raises(ConfigFileError, match="reserved"):
        load_config_document("-", environ={}, cwd=tmp_path)


def test_config_document_and_loader_require_absolute_paths(tmp_path: Path) -> None:
    with pytest.raises(ConfigFileError, match="source"):
        ConfigDocument(source=Path("config.toml"), text="")
    with pytest.raises(ConfigFileError, match="cwd"):
        load_config_document(None, environ={}, cwd=Path("relative"))
