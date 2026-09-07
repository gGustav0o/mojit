"""Shared validation and bounded allocation rules for procedural layers."""

from __future__ import annotations

import math
from numbers import Integral, Real

import numpy as np
from numpy.typing import NDArray

from mojit.core.compositor import RgbaColor
from mojit.core.models import RenderContext, Viewport

MAX_PARTICLES_PER_LAYER = 4096


class LayerInputError(ValueError):
    """Procedural layer configuration or frame input is invalid."""


def validate_context(value: object) -> RenderContext:
    """Return one validated explicit render context."""
    if not isinstance(value, RenderContext):
        raise LayerInputError("context must be a RenderContext")
    return value


def validate_seed(value: object) -> int:
    """Return a signed 64-bit deterministic seed."""
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise LayerInputError("seed must be an integer")
    seed = int(value)
    if not -(2**63) <= seed <= 2**63 - 1:
        raise LayerInputError("seed must be a signed 64-bit integer")
    return seed


def validate_real(
    value: object,
    *,
    name: str,
    minimum: float = 0.0,
    maximum: float | None = None,
) -> float:
    """Return a finite bounded real visual parameter."""
    if isinstance(value, bool) or not isinstance(value, Real):
        raise LayerInputError(f"{name} must be a real number")
    result = float(value)
    if not math.isfinite(result):
        raise LayerInputError(f"{name} must be finite")
    if result < minimum:
        raise LayerInputError(f"{name} must be >= {minimum}")
    if maximum is not None and result > maximum:
        raise LayerInputError(f"{name} must be <= {maximum}")
    return result


def validate_int(
    value: object,
    *,
    name: str,
    minimum: int = 0,
    maximum: int | None = None,
) -> int:
    """Return a strict bounded integer visual parameter."""
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise LayerInputError(f"{name} must be an integer")
    result = int(value)
    if result < minimum:
        raise LayerInputError(f"{name} must be >= {minimum}")
    if maximum is not None and result > maximum:
        raise LayerInputError(f"{name} must be <= {maximum}")
    return result


def validate_color(value: object) -> RgbaColor:
    """Return one immutable straight-alpha layer color."""
    if not isinstance(value, RgbaColor):
        raise LayerInputError("color must be an RgbaColor")
    return value


def particle_count(viewport: Viewport, density: float) -> int:
    """Derive a viewport-relative count with a hard per-layer allocation cap."""
    if density == 0.0:
        return 0
    requested = max(1, round(viewport.width_px * viewport.height_px * density))
    return min(requested, MAX_PARTICLES_PER_LAYER)


def transparent_rgba(viewport: Viewport) -> NDArray[np.uint8]:
    """Allocate one transparent full-viewport straight-alpha buffer."""
    return np.zeros((viewport.height_px, viewport.width_px, 4), dtype=np.uint8)
