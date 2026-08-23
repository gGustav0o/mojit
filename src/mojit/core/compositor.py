"""Pure full-viewport image transforms and compositing primitives."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from numbers import Integral, Real

import numpy as np
from PIL import Image, ImageFilter

from mojit.core.models import Frame, ModelValidationError, TextMask, require_int


class CompositorError(ValueError):
    """A compositor operation received incompatible or invalid input."""


def _signed_int(value: object, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise CompositorError(f"{name} must be an integer")
    return int(value)


def _finite_real(value: object, *, name: str, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise CompositorError(f"{name} must be a real number")
    converted = float(value)
    if not math.isfinite(converted):
        raise CompositorError(f"{name} must be finite")
    if positive and converted <= 0.0:
        raise CompositorError(f"{name} must be > 0")
    if not positive and converted < 0.0:
        raise CompositorError(f"{name} must be >= 0")
    return converted


@dataclass(frozen=True, slots=True)
class RgbaColor:
    """Straight-alpha 8-bit sRGB color."""

    red: int
    green: int
    blue: int
    alpha: int = 255

    def __post_init__(self) -> None:
        for name in ("red", "green", "blue", "alpha"):
            value = require_int(getattr(self, name), name=name)
            if value > 255:
                raise ModelValidationError(f"{name} must be <= 255")
            object.__setattr__(self, name, value)


@dataclass(frozen=True, slots=True)
class HorizontalBandShift:
    """One half-open source band and its clipped horizontal displacement."""

    top: int
    bottom: int
    dx_px: int

    def __post_init__(self) -> None:
        top = require_int(self.top, name="top")
        bottom = require_int(self.bottom, name="bottom")
        if bottom <= top:
            raise CompositorError("band bottom must be greater than top")
        object.__setattr__(self, "top", top)
        object.__setattr__(self, "bottom", bottom)
        object.__setattr__(self, "dx_px", _signed_int(self.dx_px, name="dx_px"))


def _require_mask(value: object, *, name: str = "mask") -> TextMask:
    if not isinstance(value, TextMask):
        raise CompositorError(f"{name} must be a TextMask")
    return value


def _require_frame(value: object, *, name: str) -> Frame:
    if not isinstance(value, Frame):
        raise CompositorError(f"{name} must be a Frame")
    return value


def _translated_alpha(alpha: np.ndarray, dx_px: int, dy_px: int) -> np.ndarray:
    height, width = alpha.shape
    output = np.zeros((height, width), dtype=np.uint8)
    copy_width = width - abs(dx_px)
    copy_height = height - abs(dy_px)
    if copy_width <= 0 or copy_height <= 0:
        return output

    source_x = max(-dx_px, 0)
    source_y = max(-dy_px, 0)
    target_x = max(dx_px, 0)
    target_y = max(dy_px, 0)
    output[target_y : target_y + copy_height, target_x : target_x + copy_width] = alpha[
        source_y : source_y + copy_height,
        source_x : source_x + copy_width,
    ]
    return output


def translate_mask(mask: TextMask, dx_px: int, dy_px: int) -> TextMask:
    """Translate a mask with clipping and transparent zero-fill."""
    source = _require_mask(mask)
    dx = _signed_int(dx_px, name="dx_px")
    dy = _signed_int(dy_px, name="dy_px")
    return TextMask(source.width, source.height, _translated_alpha(source.alpha, dx, dy))


def scale_mask_centered(mask: TextMask, factor: float) -> TextMask:
    """Scale a mask around the viewport center while retaining its canvas."""
    source = _require_mask(mask)
    scale = _finite_real(factor, name="factor", positive=True)
    target_width = max(1, round(source.width * scale))
    target_height = max(1, round(source.height * scale))
    image = Image.fromarray(source.alpha).resize(
        (target_width, target_height),
        resample=Image.Resampling.LANCZOS,
    )
    resized = np.asarray(image, dtype=np.uint8)
    output = np.zeros((source.height, source.width), dtype=np.uint8)

    copy_width = min(source.width, target_width)
    copy_height = min(source.height, target_height)
    source_x = max((target_width - source.width) // 2, 0)
    source_y = max((target_height - source.height) // 2, 0)
    target_x = max((source.width - target_width) // 2, 0)
    target_y = max((source.height - target_height) // 2, 0)
    output[target_y : target_y + copy_height, target_x : target_x + copy_width] = resized[
        source_y : source_y + copy_height,
        source_x : source_x + copy_width,
    ]
    return TextMask(source.width, source.height, output)


def blur_mask(mask: TextMask, radius_px: float) -> TextMask:
    """Apply Pillow Gaussian blur without changing viewport dimensions."""
    source = _require_mask(mask)
    radius = _finite_real(radius_px, name="radius_px")
    image = Image.fromarray(source.alpha).filter(ImageFilter.GaussianBlur(radius=radius))
    return TextMask(source.width, source.height, np.asarray(image, dtype=np.uint8))


def colorize_mask(mask: TextMask, rgba_color: RgbaColor) -> Frame:
    """Colorize mask coverage using one straight-alpha color."""
    source = _require_mask(mask)
    if not isinstance(rgba_color, RgbaColor):
        raise CompositorError("rgba_color must be an RgbaColor")

    alpha = (
        source.alpha.astype(np.uint16) * np.uint16(rgba_color.alpha) + np.uint16(127)
    ) // np.uint16(255)
    alpha = alpha.astype(np.uint8)
    rgba = np.zeros((source.height, source.width, 4), dtype=np.uint8)
    visible = alpha != 0
    rgba[visible, 0] = rgba_color.red
    rgba[visible, 1] = rgba_color.green
    rgba[visible, 2] = rgba_color.blue
    rgba[..., 3] = alpha
    return Frame(source.width, source.height, rgba)


def alpha_composite(bottom: Frame, top: Frame) -> Frame:
    """Composite two equal full-viewport frames using source-over semantics."""
    lower = _require_frame(bottom, name="bottom")
    upper = _require_frame(top, name="top")
    if (lower.width, lower.height) != (upper.width, upper.height):
        raise CompositorError("frames must have equal dimensions")

    result = Image.alpha_composite(Image.fromarray(lower.rgba), Image.fromarray(upper.rgba))
    rgba = np.array(result, dtype=np.uint8, copy=True)
    rgba[rgba[..., 3] == 0, :3] = 0
    return Frame(lower.width, lower.height, rgba)


def merge_color_channels(red: TextMask, green: TextMask, blue: TextMask) -> Frame:
    """Merge three coverage planes into one straight-alpha RGBA frame."""
    channels = (
        _require_mask(red, name="red"),
        _require_mask(green, name="green"),
        _require_mask(blue, name="blue"),
    )
    dimensions = {(channel.width, channel.height) for channel in channels}
    if len(dimensions) != 1:
        raise CompositorError("color channels must have equal dimensions")

    alpha = np.maximum.reduce(tuple(channel.alpha for channel in channels))
    rgba = np.zeros((red.height, red.width, 4), dtype=np.uint8)
    visible = alpha != 0
    denominator = alpha[visible].astype(np.uint16)
    for index, channel in enumerate(channels):
        numerator = channel.alpha[visible].astype(np.uint16) * np.uint16(255)
        rgba[..., index][visible] = ((numerator + denominator // 2) // denominator).astype(np.uint8)
    rgba[..., 3] = alpha
    return Frame(red.width, red.height, rgba)


def warp_horizontal_bands(
    mask: TextMask,
    shifts: Sequence[HorizontalBandShift],
) -> TextMask:
    """Shift non-overlapping horizontal bands while preserving all other rows."""
    source = _require_mask(mask)
    if isinstance(shifts, (str, bytes)) or not isinstance(shifts, Sequence):
        raise CompositorError("shifts must be a sequence of HorizontalBandShift")
    bands = tuple(shifts)
    if any(not isinstance(band, HorizontalBandShift) for band in bands):
        raise CompositorError("shifts must contain HorizontalBandShift values")

    previous_bottom = 0
    for band in bands:
        if band.top < previous_bottom:
            raise CompositorError("bands must be sorted and non-overlapping")
        if band.bottom > source.height:
            raise CompositorError("band exceeds mask height")
        previous_bottom = band.bottom

    output = np.array(source.alpha, dtype=np.uint8, copy=True)
    for band in bands:
        output[band.top : band.bottom] = 0
        copy_width = source.width - abs(band.dx_px)
        if copy_width <= 0:
            continue
        source_x = max(-band.dx_px, 0)
        target_x = max(band.dx_px, 0)
        output[
            band.top : band.bottom,
            target_x : target_x + copy_width,
        ] = source.alpha[
            band.top : band.bottom,
            source_x : source_x + copy_width,
        ]
    return TextMask(source.width, source.height, output)
