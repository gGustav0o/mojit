"""Validated rendering value objects and immutable ndarray contracts."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from numbers import Integral, Real

import numpy as np
from numpy.typing import NDArray

MAX_SCENE_LAYERS = 16


class ModelValidationError(ValueError):
    """A core value does not satisfy its public invariant."""


class Orientation(str, Enum):
    """Supported text-flow directions."""

    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"


def require_int(value: object, *, name: str, minimum: int = 0) -> int:
    """Return a strict integer value, excluding booleans."""
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ModelValidationError(f"{name} must be an integer")
    converted = int(value)
    if converted < minimum:
        raise ModelValidationError(f"{name} must be >= {minimum}")
    return converted


def require_real(value: object, *, name: str, minimum: float = 0.0) -> float:
    """Return a finite real value, excluding booleans."""
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ModelValidationError(f"{name} must be a real number")
    converted = float(value)
    if not math.isfinite(converted):
        raise ModelValidationError(f"{name} must be finite")
    if converted < minimum:
        raise ModelValidationError(f"{name} must be >= {minimum}")
    return converted


def _immutable_uint8_array(
    value: object,
    *,
    name: str,
    shape: tuple[int, ...],
) -> NDArray[np.uint8]:
    if not isinstance(value, np.ndarray):
        raise ModelValidationError(f"{name} must be a numpy.ndarray")
    if value.dtype != np.uint8:
        raise ModelValidationError(f"{name} must have dtype uint8")
    if value.shape != shape:
        raise ModelValidationError(f"{name} must have shape {shape}, got {value.shape}")

    contiguous = np.ascontiguousarray(value)
    storage: object = contiguous
    while isinstance(storage, np.ndarray) and storage.base is not None:
        storage = storage.base
    if not contiguous.flags.writeable and isinstance(storage, bytes):
        return contiguous
    immutable_buffer = contiguous.tobytes(order="C")
    return np.frombuffer(immutable_buffer, dtype=np.uint8).reshape(shape)


@dataclass(frozen=True, slots=True)
class Viewport:
    """Drawable viewport dimensions in pixels."""

    width_px: int
    height_px: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "width_px", require_int(self.width_px, name="width_px", minimum=1))
        object.__setattr__(
            self,
            "height_px",
            require_int(self.height_px, name="height_px", minimum=1),
        )


@dataclass(frozen=True, slots=True, eq=False)
class TextMask:
    """Full-viewport immutable alpha plane."""

    width: int
    height: int
    alpha: NDArray[np.uint8]

    __hash__ = None

    def __post_init__(self) -> None:
        width = require_int(self.width, name="width", minimum=1)
        height = require_int(self.height, name="height", minimum=1)
        alpha = _immutable_uint8_array(self.alpha, name="alpha", shape=(height, width))
        object.__setattr__(self, "width", width)
        object.__setattr__(self, "height", height)
        object.__setattr__(self, "alpha", alpha)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TextMask):
            return NotImplemented
        return (
            self.width == other.width
            and self.height == other.height
            and np.array_equal(self.alpha, other.alpha)
        )


@dataclass(frozen=True, slots=True, eq=False)
class Frame:
    """Full-viewport immutable RGBA frame."""

    width: int
    height: int
    rgba: NDArray[np.uint8]

    __hash__ = None

    def __post_init__(self) -> None:
        width = require_int(self.width, name="width", minimum=1)
        height = require_int(self.height, name="height", minimum=1)
        rgba = _immutable_uint8_array(self.rgba, name="rgba", shape=(height, width, 4))
        object.__setattr__(self, "width", width)
        object.__setattr__(self, "height", height)
        object.__setattr__(self, "rgba", rgba)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Frame):
            return NotImplemented
        return (
            self.width == other.width
            and self.height == other.height
            and np.array_equal(self.rgba, other.rgba)
        )


@dataclass(frozen=True, slots=True)
class RenderContext:
    """Deterministic inputs associated with one rendered frame."""

    viewport: Viewport
    frame_index: int
    elapsed_seconds: float

    def __post_init__(self) -> None:
        if not isinstance(self.viewport, Viewport):
            raise ModelValidationError("viewport must be a Viewport")
        object.__setattr__(
            self,
            "frame_index",
            require_int(self.frame_index, name="frame_index", minimum=0),
        )
        object.__setattr__(
            self,
            "elapsed_seconds",
            require_real(self.elapsed_seconds, name="elapsed_seconds", minimum=0.0),
        )
