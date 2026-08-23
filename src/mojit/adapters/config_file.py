"""Filesystem boundary for config discovery and bounded UTF-8 reads."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

MAX_CONFIG_BYTES = 1024 * 1024


class ConfigFileError(OSError):
    """A selected configuration file cannot be safely read."""


@dataclass(frozen=True, slots=True)
class ConfigDocument:
    """Decoded config text together with its stable absolute source path."""

    source: Path
    text: str

    def __post_init__(self) -> None:
        if not isinstance(self.source, Path) or not self.source.is_absolute():
            raise ConfigFileError("config source must be an absolute Path")
        if not isinstance(self.text, str):
            raise ConfigFileError("config text must be Unicode text")


def _selected_path(
    explicit_path: str | Path | None,
    environ: Mapping[str, str],
    cwd: Path,
) -> tuple[Path, bool] | None:
    if explicit_path is not None:
        if str(explicit_path) == "-":
            raise ConfigFileError("--config - is not supported; stdin is reserved for text")
        candidate = Path(explicit_path)
        if not candidate.is_absolute():
            candidate = cwd / candidate
        return candidate.resolve(strict=False), True

    appdata = environ.get("APPDATA")
    if not appdata:
        return None
    appdata_path = Path(appdata)
    if not appdata_path.is_absolute():
        appdata_path = cwd / appdata_path
    return (appdata_path / "mojit" / "config.toml").resolve(strict=False), False


def load_config_document(
    explicit_path: str | Path | None,
    *,
    environ: Mapping[str, str],
    cwd: Path,
) -> ConfigDocument | None:
    """Discover and read at most one configuration file."""
    if not isinstance(cwd, Path) or not cwd.is_absolute():
        raise ConfigFileError("cwd must be an absolute Path")
    selected = _selected_path(explicit_path, environ, cwd)
    if selected is None:
        return None
    path, explicit = selected

    try:
        size = path.stat().st_size
    except FileNotFoundError as error:
        if not explicit:
            return None
        raise ConfigFileError(f"config file does not exist: {path}") from error
    except OSError as error:
        raise ConfigFileError(f"cannot inspect config file: {path}") from error
    if not path.is_file():
        raise ConfigFileError(f"config path is not a file: {path}")
    if size > MAX_CONFIG_BYTES:
        raise ConfigFileError(f"config file exceeds 1 MiB: {path}")

    try:
        with path.open("rb") as stream:
            data = stream.read(MAX_CONFIG_BYTES + 1)
    except OSError as error:
        raise ConfigFileError(f"cannot read config file: {path}") from error
    if len(data) > MAX_CONFIG_BYTES:
        raise ConfigFileError(f"config file exceeds 1 MiB: {path}")
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ConfigFileError(f"config file is not valid UTF-8: {path}") from error
    return ConfigDocument(source=path, text=text)
