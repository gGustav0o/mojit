from __future__ import annotations

from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from mojit.core.compositor import (
    CompositorError,
    HorizontalBandShift,
    RgbaColor,
    alpha_composite,
    alpha_composite_many,
    blur_mask,
    colorize_mask,
    composite_colorized_masks,
    merge_color_channels,
    scale_mask_centered,
    translate_mask,
    warp_horizontal_bands,
)
from mojit.core.models import Frame, ModelValidationError, TextMask


def _mask(alpha: np.ndarray | None = None) -> TextMask:
    values = np.zeros((4, 5), dtype=np.uint8) if alpha is None else alpha
    return TextMask(width=5, height=4, alpha=values)


def test_rgba_color_is_strict_and_frozen() -> None:
    color = RgbaColor(np.int64(1), 2, 3, 4)
    assert color == RgbaColor(1, 2, 3, 4)
    with pytest.raises(FrozenInstanceError):
        color.red = 5  # type: ignore[misc]


@pytest.mark.parametrize("value", [-1, 256, True, 1.5, "1"])
def test_rgba_color_rejects_invalid_channels(value: object) -> None:
    with pytest.raises(ModelValidationError):
        RgbaColor(value, 0, 0)  # type: ignore[arg-type]


def test_translate_clips_without_wrapping_or_mutating() -> None:
    alpha = np.arange(1, 21, dtype=np.uint8).reshape(4, 5)
    source = _mask(alpha)

    positive = translate_mask(source, 2, 1)
    negative = translate_mask(source, -1, -2)

    assert np.array_equal(positive.alpha[1:, 2:], alpha[:-1, :-2])
    assert np.count_nonzero(positive.alpha[:1]) == 0
    assert np.count_nonzero(positive.alpha[:, :2]) == 0
    assert np.array_equal(negative.alpha[:-2, :-1], alpha[2:, 1:])
    assert np.array_equal(source.alpha, alpha)
    assert not positive.alpha.flags.writeable


def test_translate_outside_canvas_returns_transparent_mask() -> None:
    source = _mask(np.full((4, 5), 255, dtype=np.uint8))
    assert np.count_nonzero(translate_mask(source, 5, 0).alpha) == 0
    assert np.count_nonzero(translate_mask(source, 0, -4).alpha) == 0


@pytest.mark.parametrize(("dx", "dy"), [(True, 0), (0, 1.5), ("1", 0)])
def test_translate_rejects_non_integer_offsets(dx: object, dy: object) -> None:
    with pytest.raises(CompositorError):
        translate_mask(_mask(), dx, dy)  # type: ignore[arg-type]


def test_centered_scale_retains_canvas_and_owned_storage() -> None:
    alpha = np.zeros((4, 5), dtype=np.uint8)
    alpha[1:3, 1:4] = 255
    source = _mask(alpha)

    identity = scale_mask_centered(source, 1.0)
    smaller = scale_mask_centered(source, 0.5)
    larger = scale_mask_centered(source, 2.0)

    assert identity == source
    assert smaller.alpha.shape == larger.alpha.shape == (4, 5)
    assert np.count_nonzero(smaller.alpha) > 0
    assert np.count_nonzero(larger.alpha) > 0
    assert not np.shares_memory(identity.alpha, source.alpha)


@pytest.mark.parametrize("factor", [0, -1, True, float("nan"), float("inf"), "1"])
def test_scale_rejects_invalid_factors(factor: object) -> None:
    with pytest.raises(CompositorError):
        scale_mask_centered(_mask(), factor)  # type: ignore[arg-type]


def test_blur_spreads_alpha_and_zero_radius_is_identity() -> None:
    alpha = np.zeros((4, 5), dtype=np.uint8)
    alpha[2, 2] = 255
    source = _mask(alpha)

    assert blur_mask(source, 0) == source
    blurred = blur_mask(source, 1.0)
    assert blurred.alpha[2, 2] < 255
    assert np.count_nonzero(blurred.alpha) > 1


@pytest.mark.parametrize("radius", [-1, True, float("nan"), float("inf"), "1"])
def test_blur_rejects_invalid_radius(radius: object) -> None:
    with pytest.raises(CompositorError):
        blur_mask(_mask(), radius)  # type: ignore[arg-type]


def test_colorize_uses_straight_alpha_and_zeroes_transparent_rgb() -> None:
    alpha = np.zeros((4, 5), dtype=np.uint8)
    alpha[1, 1] = 128
    frame = colorize_mask(_mask(alpha), RgbaColor(10, 20, 30, 128))

    assert frame.rgba[1, 1].tolist() == [10, 20, 30, 64]
    assert frame.rgba[0, 0].tolist() == [0, 0, 0, 0]
    assert not frame.rgba.flags.writeable


def test_colorize_requires_domain_values() -> None:
    with pytest.raises(CompositorError, match="TextMask"):
        colorize_mask(object(), RgbaColor(0, 0, 0))  # type: ignore[arg-type]
    with pytest.raises(CompositorError, match="RgbaColor"):
        colorize_mask(_mask(), (0, 0, 0, 255))  # type: ignore[arg-type]


def test_alpha_composite_is_source_over_and_sanitizes_transparent_rgb() -> None:
    bottom_values = np.zeros((1, 1, 4), dtype=np.uint8)
    bottom_values[0, 0] = [255, 0, 0, 255]
    top_values = np.zeros((1, 1, 4), dtype=np.uint8)
    top_values[0, 0] = [0, 0, 255, 128]
    result = alpha_composite(Frame(1, 1, bottom_values), Frame(1, 1, top_values))
    assert result.rgba[0, 0].tolist() == [127, 0, 128, 255]

    hidden_rgb = np.array([[[255, 1, 2, 0]]], dtype=np.uint8)
    transparent = alpha_composite(Frame(1, 1, hidden_rgb), Frame(1, 1, hidden_rgb))
    assert transparent.rgba[0, 0].tolist() == [0, 0, 0, 0]


def test_alpha_composite_rejects_wrong_or_mismatched_frames() -> None:
    frame = Frame(1, 1, np.zeros((1, 1, 4), dtype=np.uint8))
    other = Frame(2, 1, np.zeros((1, 2, 4), dtype=np.uint8))
    with pytest.raises(CompositorError, match="Frame"):
        alpha_composite(object(), frame)  # type: ignore[arg-type]
    with pytest.raises(CompositorError, match="equal"):
        alpha_composite(frame, other)


def test_alpha_composite_many_matches_pairwise_bytes_and_preserves_single_frame() -> None:
    frames = []
    for rgba in ((255, 0, 0, 255), (0, 255, 0, 96), (0, 0, 255, 128)):
        values = np.empty((2, 3, 4), dtype=np.uint8)
        values[:] = rgba
        frames.append(Frame(3, 2, values))

    expected = alpha_composite(alpha_composite(frames[0], frames[1]), frames[2])
    assert alpha_composite_many(frames) == expected
    assert alpha_composite_many((frames[0],)) is frames[0]


def test_alpha_composite_many_rejects_invalid_sequences() -> None:
    frame = Frame(1, 1, np.zeros((1, 1, 4), dtype=np.uint8))
    other = Frame(2, 1, np.zeros((1, 2, 4), dtype=np.uint8))
    with pytest.raises(CompositorError, match="sequence"):
        alpha_composite_many("bad")  # type: ignore[arg-type]
    with pytest.raises(CompositorError, match="empty"):
        alpha_composite_many(())
    with pytest.raises(CompositorError, match="Frame"):
        alpha_composite_many((frame, object()))  # type: ignore[arg-type]
    with pytest.raises(CompositorError, match="equal"):
        alpha_composite_many((frame, other))


def test_composite_colorized_masks_matches_individual_frame_composition() -> None:
    first_alpha = np.arange(20, dtype=np.uint8).reshape(4, 5) * 12
    second_alpha = np.flip(first_alpha, axis=1).copy()
    contributions = (
        (_mask(first_alpha), RgbaColor(10, 90, 220, 73)),
        (_mask(second_alpha), RgbaColor(240, 80, 20, 181)),
        (_mask(np.full((4, 5), 33, dtype=np.uint8)), RgbaColor(255, 255, 255)),
    )
    expected = alpha_composite_many(
        tuple(colorize_mask(mask, color) for mask, color in contributions)
    )

    actual = composite_colorized_masks(contributions)

    assert actual == expected
    assert not actual.rgba.flags.writeable


def test_composite_colorized_masks_rejects_invalid_contributions() -> None:
    color = RgbaColor(1, 2, 3)
    with pytest.raises(CompositorError, match="sequence"):
        composite_colorized_masks("bad")  # type: ignore[arg-type]
    with pytest.raises(CompositorError, match="empty"):
        composite_colorized_masks(())
    with pytest.raises(CompositorError, match="pair"):
        composite_colorized_masks(((_mask(),),))  # type: ignore[arg-type]
    with pytest.raises(CompositorError, match="TextMask"):
        composite_colorized_masks(((object(), color),))  # type: ignore[arg-type]
    with pytest.raises(CompositorError, match="RgbaColor"):
        composite_colorized_masks(((_mask(), object()),))  # type: ignore[arg-type]
    with pytest.raises(CompositorError, match="equal"):
        small = TextMask(1, 1, np.zeros((1, 1), dtype=np.uint8))
        composite_colorized_masks(((_mask(), color), (small, color)))


def test_merge_color_channels_normalizes_straight_color() -> None:
    red = np.zeros((4, 5), dtype=np.uint8)
    green = red.copy()
    blue = red.copy()
    red[1, 1] = 64
    green[1, 1] = 128
    frame = merge_color_channels(_mask(red), _mask(green), _mask(blue))

    assert frame.rgba[1, 1].tolist() == [128, 255, 0, 128]
    assert frame.rgba[0, 0].tolist() == [0, 0, 0, 0]


def test_merge_color_channels_requires_equal_masks() -> None:
    small = TextMask(1, 1, np.zeros((1, 1), dtype=np.uint8))
    with pytest.raises(CompositorError, match="equal"):
        merge_color_channels(_mask(), _mask(), small)
    with pytest.raises(CompositorError, match="TextMask"):
        merge_color_channels(_mask(), object(), _mask())  # type: ignore[arg-type]


def test_horizontal_band_shift_is_strict() -> None:
    assert HorizontalBandShift(0, 1, -2).dx_px == -2
    with pytest.raises(CompositorError, match="greater"):
        HorizontalBandShift(1, 1, 0)
    with pytest.raises(CompositorError, match="integer"):
        HorizontalBandShift(0, 1, True)


def test_band_warp_shifts_only_selected_rows() -> None:
    alpha = np.arange(1, 21, dtype=np.uint8).reshape(4, 5)
    result = warp_horizontal_bands(
        _mask(alpha),
        (HorizontalBandShift(0, 1, 2), HorizontalBandShift(2, 4, -1)),
    )

    assert result.alpha[0].tolist() == [0, 0, 1, 2, 3]
    assert result.alpha[1].tolist() == alpha[1].tolist()
    assert result.alpha[2].tolist() == [12, 13, 14, 15, 0]
    assert result.alpha[3].tolist() == [17, 18, 19, 20, 0]


def test_band_warp_rejects_invalid_sequences() -> None:
    with pytest.raises(CompositorError, match="sequence"):
        warp_horizontal_bands(_mask(), "bad")  # type: ignore[arg-type]
    with pytest.raises(CompositorError, match="contain"):
        warp_horizontal_bands(_mask(), (object(),))  # type: ignore[arg-type]
    with pytest.raises(CompositorError, match="non-overlapping"):
        warp_horizontal_bands(_mask(), (HorizontalBandShift(1, 3, 1), HorizontalBandShift(2, 4, 1)))
    with pytest.raises(CompositorError, match="height"):
        warp_horizontal_bands(_mask(), (HorizontalBandShift(3, 5, 1),))


def test_compositor_rejects_non_mask_transforms() -> None:
    with pytest.raises(CompositorError, match="TextMask"):
        translate_mask(object(), 0, 0)  # type: ignore[arg-type]
