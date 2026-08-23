from __future__ import annotations

import math

import pytest

from mojit.core.layout import (
    InkBounds,
    LayoutError,
    PixelBox,
    TextDoesNotFitError,
    available_box,
    centered_origin,
    fits,
    largest_fitting_font_size,
    validate_margin,
)
from mojit.core.models import ModelValidationError, Viewport


def test_available_box_reserves_ceil_margin_on_each_edge() -> None:
    assert available_box(Viewport(101, 99), 0.08) == PixelBox(9, 8, 92, 91)


@pytest.mark.parametrize("margin", [-0.1, 0.5, 1.0, True, float("nan"), float("inf")])
def test_margin_validation_rejects_invalid_values(margin: object) -> None:
    with pytest.raises(ModelValidationError):
        validate_margin(margin)  # type: ignore[arg-type]


def test_margin_can_leave_no_drawable_pixel() -> None:
    with pytest.raises(LayoutError, match="no drawable pixels"):
        available_box(Viewport(1, 1), 0.1)


@pytest.mark.parametrize(
    "box",
    [PixelBox(0, 0, 0, 0), PixelBox(1, 1, 1, 1)],
)
def test_empty_pixel_boxes_are_representable(box: PixelBox) -> None:
    assert box.width == 0
    assert box.height == 0


@pytest.mark.parametrize("values", [(2, 0, 1, 1), (0, 2, 1, 1)])
def test_pixel_box_rejects_reversed_edges(values: tuple[int, int, int, int]) -> None:
    with pytest.raises(ModelValidationError):
        PixelBox(*values)


@pytest.mark.parametrize("values", [(0, 0, 0, 1), (0, 0, 1, 0), (False, 0, 1, 1)])
def test_ink_bounds_require_positive_integer_dimensions(
    values: tuple[object, object, object, object],
) -> None:
    with pytest.raises((LayoutError, ModelValidationError)):
        InkBounds(*values)  # type: ignore[arg-type]


def test_centered_origin_corrects_negative_bearings() -> None:
    available = PixelBox(10, 20, 111, 101)
    ink = InkBounds(-3, -5, 37, 25)

    origin = centered_origin(ink, available)

    assert origin.x + ink.left == 40
    assert origin.y + ink.top == 45
    assert fits(ink, available)


def test_centering_rejects_oversized_ink() -> None:
    with pytest.raises(TextDoesNotFitError):
        centered_origin(InkBounds(0, 0, 101, 10), PixelBox(0, 0, 100, 100))


def test_font_size_search_returns_the_largest_fit_logarithmically() -> None:
    calls: list[int] = []

    def measure(size: int) -> InkBounds:
        calls.append(size)
        return InkBounds(-1, -2, size * 3 - 1, size * 2 - 2)

    size, ink = largest_fitting_font_size(measure, PixelBox(0, 0, 100, 80))

    assert size == 33
    assert ink.width == 99
    assert len(calls) <= 2 * math.ceil(math.log2(size)) + 2
    assert len(calls) == len(set(calls))


def test_font_size_search_fails_when_size_one_does_not_fit() -> None:
    with pytest.raises(TextDoesNotFitError, match="minimum"):
        largest_fitting_font_size(
            lambda _: InkBounds(0, 0, 101, 1),
            PixelBox(0, 0, 100, 100),
        )


def test_font_size_search_honors_explicit_safety_bound() -> None:
    size, _ = largest_fitting_font_size(
        lambda value: InkBounds(0, 0, value, value),
        PixelBox(0, 0, 100, 100),
        maximum_size=16,
    )

    assert size == 16


def test_font_size_search_supports_a_unit_safety_bound() -> None:
    bounds = InkBounds(0, 0, 1, 1)

    assert largest_fitting_font_size(
        lambda _: bounds,
        PixelBox(0, 0, 1, 1),
        maximum_size=1,
    ) == (1, bounds)
