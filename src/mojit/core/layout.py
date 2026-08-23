"""Pure viewport, margin, placement, and font-size calculations."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from numbers import Real

from mojit.core.models import ModelValidationError, Viewport, require_int


class LayoutError(ValueError):
    """Base error for an unsatisfied layout contract."""


class TextDoesNotFitError(LayoutError):
    """No positive font size fits the available viewport."""


@dataclass(frozen=True, slots=True)
class PixelBox:
    """Integer pixel rectangle with exclusive right and bottom edges."""

    left: int
    top: int
    right: int
    bottom: int

    def __post_init__(self) -> None:
        for name in ("left", "top", "right", "bottom"):
            object.__setattr__(self, name, require_int(getattr(self, name), name=name))
        if self.right < self.left:
            raise ModelValidationError("right must be >= left")
        if self.bottom < self.top:
            raise ModelValidationError("bottom must be >= top")

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top


@dataclass(frozen=True, slots=True)
class InkBounds:
    """Pillow-compatible ink bounds, including possibly negative bearings."""

    left: int
    top: int
    right: int
    bottom: int

    def __post_init__(self) -> None:
        for name in ("left", "top", "right", "bottom"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ModelValidationError(f"{name} must be an integer")
        if self.width <= 0 or self.height <= 0:
            raise LayoutError("ink bounds must have positive width and height")

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top


@dataclass(frozen=True, slots=True)
class Point:
    """Integer drawing origin."""

    x: int
    y: int


MeasureText = Callable[[int], InkBounds]


def validate_margin(margin: float) -> float:
    if isinstance(margin, bool) or not isinstance(margin, Real):
        raise ModelValidationError("margin must be a real number")
    normalized = float(margin)
    if not math.isfinite(normalized) or not 0.0 <= normalized < 0.5:
        raise ModelValidationError("margin must be finite and satisfy 0 <= margin < 0.5")
    return normalized


def available_box(viewport: Viewport, margin: float) -> PixelBox:
    """Reserve at least the requested margin fraction on every edge."""
    normalized_margin = validate_margin(margin)
    horizontal = math.ceil(viewport.width_px * normalized_margin)
    vertical = math.ceil(viewport.height_px * normalized_margin)
    if viewport.width_px - 2 * horizontal <= 0 or viewport.height_px - 2 * vertical <= 0:
        raise LayoutError("margin leaves no drawable pixels")
    box = PixelBox(
        left=horizontal,
        top=vertical,
        right=viewport.width_px - horizontal,
        bottom=viewport.height_px - vertical,
    )
    return box


def fits(ink: InkBounds, available: PixelBox) -> bool:
    """Return whether ink dimensions fit without clipping."""
    return ink.width <= available.width and ink.height <= available.height


def centered_origin(ink: InkBounds, available: PixelBox) -> Point:
    """Center ink with floor-biased placement for an odd spare pixel."""
    if not fits(ink, available):
        raise TextDoesNotFitError("ink does not fit the available box")
    target_left = available.left + (available.width - ink.width) // 2
    target_top = available.top + (available.height - ink.height) // 2
    return Point(x=target_left - ink.left, y=target_top - ink.top)


def largest_fitting_font_size(
    measure: MeasureText,
    available: PixelBox,
    *,
    maximum_size: int = 65_536,
) -> tuple[int, InkBounds]:
    """Find the maximum fitting size for a monotonic measurer in O(log result)."""
    maximum = require_int(maximum_size, name="maximum_size", minimum=1)
    measured: dict[int, InkBounds] = {}

    def at(size: int) -> InkBounds:
        if size not in measured:
            measured[size] = measure(size)
        return measured[size]

    first = at(1)
    if not fits(first, available):
        raise TextDoesNotFitError("text does not fit at the minimum font size")
    if maximum == 1:
        return 1, first

    low = 1
    high = 2
    while high < maximum and fits(at(high), available):
        low = high
        high = min(high * 2, maximum)

    high_ink = at(high)
    if fits(high_ink, available):
        return high, high_ink

    while low + 1 < high:
        middle = (low + high) // 2
        if fits(at(middle), available):
            low = middle
        else:
            high = middle
    return low, at(low)
