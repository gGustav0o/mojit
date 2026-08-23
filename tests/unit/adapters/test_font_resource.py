from __future__ import annotations

from pathlib import Path

import pytest

from mojit.adapters.font_resource import FontResourceError, load_font_resource


def test_font_resource_rejects_missing_path(tmp_path: Path) -> None:
    with pytest.raises(FontResourceError, match="does not exist"):
        load_font_resource(tmp_path / "missing.ttf")


def test_font_resource_rejects_directory(tmp_path: Path) -> None:
    with pytest.raises(FontResourceError, match="not a file"):
        load_font_resource(tmp_path)


def test_font_resource_rejects_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "empty.ttf"
    path.touch()

    with pytest.raises(FontResourceError, match="empty"):
        load_font_resource(path)


def test_font_resource_rejects_invalid_font(tmp_path: Path) -> None:
    path = tmp_path / "invalid.ttf"
    path.write_bytes(b"not a font")

    with pytest.raises(FontResourceError, match="invalid font"):
        load_font_resource(path)


@pytest.mark.parametrize("path", ["", "  ", 1, object()])
def test_font_resource_rejects_invalid_path_value(path: object) -> None:
    with pytest.raises(FontResourceError):
        load_font_resource(path)  # type: ignore[arg-type]
