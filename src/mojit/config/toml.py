"""Pure strict decoding of a TOML configuration document."""

from __future__ import annotations

import tomllib

from mojit.config.models import ConfigOverrides, ConfigValidationError
from mojit.core.models import Orientation

_ALLOWED_KEYS = frozenset(
    {
        "effect",
        "orientation",
        "font",
        "fps",
        "margin",
        "seed",
        "scene",
        "scene_version",
        "layers",
    }
)


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

    for key in ("effect", "orientation", "font", "scene"):
        _require_exact_type(values, key, str)
    for key in ("fps", "seed"):
        _require_exact_type(values, key, int)
    if "margin" in values and type(values["margin"]) not in (int, float):
        raise ConfigValidationError("config key 'margin' must be int or float")

    has_version = "scene_version" in values
    has_layers = "layers" in values
    if has_version != has_layers:
        raise ConfigValidationError("scene_version and layers must be provided together")
    if has_version:
        _require_exact_type(values, "scene_version", int)
        if values["scene_version"] != 1:
            raise ConfigValidationError("scene_version must be 1")
        if type(values["layers"]) is not list or any(
            type(layer) is not str for layer in values["layers"]
        ):
            raise ConfigValidationError("config key 'layers' must be an array of strings")
    if "scene" in values and has_version:
        raise ConfigValidationError("scene and custom scene layers are mutually exclusive")

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
        scene=values.get("scene"),
        scene_layers=tuple(values["layers"]) if has_layers else None,
    )
