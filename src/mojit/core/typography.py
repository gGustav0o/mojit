"""Pillow-backed text measurement and alpha-mask rasterization."""

from __future__ import annotations

import hashlib
import io
import re
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from PIL import features as pil_features

from mojit.core.layout import (
    InkBounds,
    PixelBox,
    TextDoesNotFitError,
    available_box,
    centered_origin,
    largest_fitting_font_size,
    validate_margin,
)
from mojit.core.models import ModelValidationError, Orientation, TextMask, Viewport
from mojit.core.text_layout import (
    TextLines,
    TextPhrases,
    horizontal_line_candidates,
    validate_text_phrases,
)

_SHA256 = re.compile(r"[0-9a-f]{64}")
_LINE_SPACING_RATIO = 0.15


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
        if "\0" in self.text or "\r" in self.text or "\n" in self.text:
            raise InvalidTextError("text must be one NUL-free line")
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


@dataclass(frozen=True, slots=True)
class _FittedText:
    lines: TextLines
    font_size: int
    ink: InkBounds
    spacing: int


FontAt = Callable[[int], ImageFont.FreeTypeFont]


def _line_spacing(font_size: int, line_count: int) -> int:
    return max(1, round(font_size * _LINE_SPACING_RATIO)) if line_count > 1 else 0


def _measure_lines(
    draw: ImageDraw.ImageDraw,
    lines: TextLines,
    font: ImageFont.FreeTypeFont,
    options: dict[str, object],
    spacing: int,
) -> InkBounds:
    text = "\n".join(lines)
    try:
        if len(lines) == 1:
            bounds = draw.textbbox((0, 0), text, font=font, **options)
        else:
            bounds = draw.multiline_textbbox(
                (0, 0),
                text,
                font=font,
                spacing=spacing,
                align="center",
                **options,
            )
    except (KeyError, TypeError, ValueError) as error:
        raise TypographyError(f"text measurement failed: {error}") from error
    return InkBounds(*(int(value) for value in bounds))


def _draw_lines(
    draw: ImageDraw.ImageDraw,
    origin: tuple[int, int],
    fitted: _FittedText,
    font: ImageFont.FreeTypeFont,
    options: dict[str, object],
) -> None:
    text = "\n".join(fitted.lines)
    try:
        if len(fitted.lines) == 1:
            draw.text(origin, text, fill=255, font=font, **options)
        else:
            draw.multiline_text(
                origin,
                text,
                fill=255,
                font=font,
                spacing=fitted.spacing,
                align="center",
                **options,
            )
    except (KeyError, TypeError, ValueError) as error:
        raise TypographyError(f"text rasterization failed: {error}") from error


def _fit_lines(
    draw: ImageDraw.ImageDraw,
    lines: TextLines,
    available: PixelBox,
    font_at: FontAt,
    options: dict[str, object],
) -> _FittedText:
    line_count = len(lines)

    def measure(size: int) -> InkBounds:
        return _measure_lines(
            draw,
            lines,
            font_at(size),
            options,
            _line_spacing(size, line_count),
        )

    font_size, ink = largest_fitting_font_size(measure, available)
    return _FittedText(
        lines=lines,
        font_size=font_size,
        ink=ink,
        spacing=_line_spacing(font_size, line_count),
    )


def rasterize_text_mask(
    font_data: bytes,
    key: TypographyKey,
    *,
    phrases: TextPhrases,
) -> TextMask:
    """Render a deterministic, centered alpha mask in full-viewport coordinates."""
    candidates = (
        horizontal_line_candidates(key.text, phrases=phrases)
        if key.orientation is Orientation.HORIZONTAL
        else ((key.text,),)
    )
    if key.orientation is Orientation.VERTICAL:
        validate_text_phrases(key.text, phrases)
    if not isinstance(font_data, bytes) or not font_data:
        raise FontDataError("font_data must be non-empty bytes")
    if hashlib.sha256(font_data).hexdigest() != key.font_fingerprint:
        raise FontDataError("font data does not match font_fingerprint")
    require_shaping_capability()

    available = available_box(key.viewport, key.margin)
    options = _options(key)
    measurement_surface = Image.new("L", (1, 1), 0)
    measurement_draw = ImageDraw.Draw(measurement_surface)
    fonts: dict[int, ImageFont.FreeTypeFont] = {}

    def font_at(size: int) -> ImageFont.FreeTypeFont:
        if size not in fonts:
            fonts[size] = _load_font(font_data, size)
        return fonts[size]

    fitted_candidates: list[_FittedText] = []
    for lines in candidates:
        try:
            fitted = _fit_lines(
                measurement_draw,
                lines,
                available,
                font_at,
                options,
            )
        except TextDoesNotFitError:
            continue
        fitted_candidates.append(fitted)

    if not fitted_candidates:
        raise TextDoesNotFitError("text does not fit at the minimum font size")
    fitted = max(
        fitted_candidates,
        key=lambda candidate: (candidate.font_size, -len(candidate.lines)),
    )
    origin = centered_origin(fitted.ink, available)
    image = Image.new("L", (key.viewport.width_px, key.viewport.height_px), 0)
    draw = ImageDraw.Draw(image)
    _draw_lines(
        draw,
        (origin.x, origin.y),
        fitted,
        font_at(fitted.font_size),
        options,
    )

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
