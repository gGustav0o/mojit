"""Pure strict decoding of a TOML configuration document."""

from __future__ import annotations

import tomllib

from mojit.config.models import ConfigOverrides, ConfigValidationError
from mojit.core.models import Orientation

_ALLOWED_KEYS = frozenset({"effect", "orientation", "font", "fps", "margin", "seed"})


class ConfigSyntaxError(ValueError):
    """A configuration document is not valid TOML."""


def _require_exact_type(values: dict[str, object], key: str, expected: type) -> None:
    if key in values and type(values[key]) is not expected:
        raise ConfigValidationError(f"config key {key!r} must be {expected.__name__}")


def parse_toml_config(document: str | bytes) -> ConfigOverrides:
    """Decode one complete TOML document without filesystem access."""
    if isinstance(document, bytes):
        try:
            source = document.decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise ConfigSyntaxError("config file is not valid UTF-8") from error
    elif isinstance(document, str):
        source = document
    else:
        raise TypeError("document must be str or bytes")

    try:
        values = tomllib.loads(source)
    except tomllib.TOMLDecodeError as error:
        raise ConfigSyntaxError(f"invalid TOML: {error}") from error

    unknown = sorted(values.keys() - _ALLOWED_KEYS)
    if unknown:
        raise ConfigValidationError(f"unknown config key: {unknown[0]}")

    for key in ("effect", "orientation", "font"):
        _require_exact_type(values, key, str)
    for key in ("fps", "seed"):
        _require_exact_type(values, key, int)
    if "margin" in values and type(values["margin"]) not in (int, float):
        raise ConfigValidationError("config key 'margin' must be int or float")

    orientation = None
    if "orientation" in values:
        try:
            orientation = Orientation(values["orientation"])
        except ValueError as error:
            raise ConfigValidationError(
                "config key 'orientation' must be horizontal or vertical"
            ) from error

    return ConfigOverrides(
        effect=values.get("effect"),
        orientation=orientation,
        font=values.get("font"),
        fps=values.get("fps"),
        margin=values.get("margin"),
        seed=values.get("seed"),
    )
