"""Pillow-backed text measurement and alpha-mask rasterization."""

from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from PIL import features as pil_features

from mojit.core.layout import (
    InkBounds,
    available_box,
    centered_origin,
    largest_fitting_font_size,
    validate_margin,
)
from mojit.core.models import ModelValidationError, Orientation, TextMask, Viewport

_SHA256 = re.compile(r"[0-9a-f]{64}")


class TypographyError(ValueError):
    """Base error for typography input or rendering failures."""


class InvalidTextError(TypographyError):
    """Text has no renderable content."""


class FontDataError(TypographyError):
    """Font bytes are invalid or do not match their identity."""


class ShapingUnavailableError(TypographyError):
    """The required Raqm/FriBiDi shaping path is unavailable."""


@dataclass(frozen=True, slots=True)
class TypographyKey:
    """Complete immutable identity of a text mask."""

    text: str
    font_fingerprint: str
    orientation: Orientation
    viewport: Viewport
    margin: float
    language: str = "ja"
    features: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text or self.text.isspace():
            raise InvalidTextError("text must contain at least one visible character")
        if not isinstance(self.font_fingerprint, str) or not _SHA256.fullmatch(
            self.font_fingerprint
        ):
            raise FontDataError("font_fingerprint must be a lowercase SHA-256 digest")
        if not isinstance(self.orientation, Orientation):
            raise ModelValidationError("orientation must be an Orientation")
        if not isinstance(self.viewport, Viewport):
            raise ModelValidationError("viewport must be a Viewport")
        object.__setattr__(self, "margin", validate_margin(self.margin))
        if not isinstance(self.language, str) or not self.language.strip():
            raise ModelValidationError("language must be a non-empty string")
        if isinstance(self.features, str) or not isinstance(self.features, (tuple, list)):
            raise ModelValidationError("features must be a tuple or list of strings")
        normalized_features = tuple(self.features)
        if any(not isinstance(item, str) or not item for item in normalized_features):
            raise ModelValidationError("features must contain non-empty strings")
        object.__setattr__(self, "features", normalized_features)

    @property
    def direction(self) -> str:
        return "ttb" if self.orientation is Orientation.VERTICAL else "ltr"


def require_shaping_capability() -> None:
    """Fail early when the required Raqm/FriBiDi shaping path is unavailable."""
    try:
        available = pil_features.check_feature("raqm")
    except (ValueError, TypeError):
        available = False
    if not available:
        raise ShapingUnavailableError(
            "Pillow Raqm/FriBiDi support is required; install the application FriBiDi runtime"
        )


def _load_font(font_data: bytes, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(
            io.BytesIO(font_data),
            size=size,
            layout_engine=ImageFont.Layout.RAQM,
        )
    except (OSError, ValueError) as error:
        raise FontDataError("font data cannot be loaded by Pillow/FreeType") from error


def _options(key: TypographyKey) -> dict[str, object]:
    return {
        "direction": key.direction,
        "language": key.language,
        "features": list(key.features) or None,
    }


def rasterize_text_mask(font_data: bytes, key: TypographyKey) -> TextMask:
    """Render a deterministic, centered alpha mask in full-viewport coordinates."""
    if not isinstance(font_data, bytes) or not font_data:
        raise FontDataError("font_data must be non-empty bytes")
    if hashlib.sha256(font_data).hexdigest() != key.font_fingerprint:
        raise FontDataError("font data does not match font_fingerprint")
    require_shaping_capability()

    available = available_box(key.viewport, key.margin)
    options = _options(key)
    measurement_surface = Image.new("L", (1, 1), 0)
    measurement_draw = ImageDraw.Draw(measurement_surface)

    def measure(size: int) -> InkBounds:
        font = _load_font(font_data, size)
        try:
            bounds = measurement_draw.textbbox((0, 0), key.text, font=font, **options)
        except (KeyError, TypeError, ValueError) as error:
            raise TypographyError(f"text measurement failed: {error}") from error
        return InkBounds(*(int(value) for value in bounds))

    font_size, ink = largest_fitting_font_size(measure, available)
    origin = centered_origin(ink, available)
    font = _load_font(font_data, font_size)
    image = Image.new("L", (key.viewport.width_px, key.viewport.height_px), 0)
    draw = ImageDraw.Draw(image)
    try:
        draw.text((origin.x, origin.y), key.text, fill=255, font=font, **options)
    except (KeyError, TypeError, ValueError) as error:
        raise TypographyError(f"text rasterization failed: {error}") from error

    alpha = np.asarray(image, dtype=np.uint8)
    nonzero_y, nonzero_x = np.nonzero(alpha)
    if nonzero_x.size == 0:
        raise InvalidTextError("text produced no visible glyph ink")
    if (
        int(nonzero_x.min()) < available.left
        or int(nonzero_x.max()) >= available.right
        or int(nonzero_y.min()) < available.top
        or int(nonzero_y.max()) >= available.bottom
    ):
        raise TypographyError("rasterized glyph ink escaped the fitted layout bounds")

    return TextMask(
        width=key.viewport.width_px,
        height=key.viewport.height_px,
        alpha=alpha,
    )
