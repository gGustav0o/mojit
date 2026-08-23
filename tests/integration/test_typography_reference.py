from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest
from PIL import features as pil_features

from mojit.adapters.font_resource import load_font_resource
from mojit.core.layout import available_box
from mojit.core.models import Orientation, TextMask, Viewport
from mojit.core.typography import TypographyKey, rasterize_text_mask

REFERENCE_FONT = Path("C:/Windows/Fonts/YuGothB.ttc")
REFERENCE_FONT_SHA256 = "d923a57f781f06198167da4f58287be7ac64a954a47aff4295e078a42b4b68b2"
REFERENCE_MASK_SHA256 = {
    Orientation.HORIZONTAL: "e8ebd18622031f116cf3923a4ad5e61491465a56f4b2576bff145ee307db55d4",
    Orientation.VERTICAL: "21e3891463598eda610c46aab678c27b8e6b63f9df37e4e4f2755bc057d56b03",
}


def _reference_font():
    if not REFERENCE_FONT.is_file():
        pytest.skip(f"reference font is absent: {REFERENCE_FONT}")
    if not pil_features.check_feature("raqm"):
        pytest.skip("Pillow Raqm/FriBiDi capability is unavailable")
    resource = load_font_resource(REFERENCE_FONT)
    if resource.fingerprint != REFERENCE_FONT_SHA256:
        pytest.skip("reference font checksum differs from the Phase 0 baseline")
    return resource


def _mask(
    text: str,
    orientation: Orientation,
    viewport: Viewport,
) -> TextMask:
    resource = _reference_font()
    key = TypographyKey(
        text=text,
        font_fingerprint=resource.fingerprint,
        orientation=orientation,
        viewport=viewport,
        margin=0.08,
    )
    return rasterize_text_mask(resource.data, key)


def _digest(mask: TextMask) -> str:
    return hashlib.sha256(mask.alpha.tobytes()).hexdigest()


def _assert_ink_inside_margin(mask: TextMask, margin: float) -> None:
    available = available_box(Viewport(mask.width, mask.height), margin)
    rows, columns = np.nonzero(mask.alpha)

    assert columns.size > 0
    assert int(columns.min()) >= available.left
    assert int(columns.max()) < available.right
    assert int(rows.min()) >= available.top
    assert int(rows.max()) < available.bottom


@pytest.mark.typography_reference
@pytest.mark.parametrize(
    ("text", "orientation"),
    [
        ("電脳世界", Orientation.HORIZONTAL),
        ("警告、「猫」。", Orientation.VERTICAL),
    ],
)
def test_reference_masks_are_deterministic_and_unclipped(
    text: str,
    orientation: Orientation,
) -> None:
    viewport = Viewport(640, 384)

    first = _mask(text, orientation, viewport)
    second = _mask(text, orientation, viewport)

    assert first == second
    assert _digest(first) == _digest(second)
    assert _digest(first) == REFERENCE_MASK_SHA256[orientation]
    assert first.alpha.shape == (viewport.height_px, viewport.width_px)
    assert not first.alpha.flags.writeable
    _assert_ink_inside_margin(first, 0.08)


@pytest.mark.typography_reference
@pytest.mark.parametrize("orientation", list(Orientation))
def test_reference_typography_adapts_to_viewport(orientation: Orientation) -> None:
    text = "電脳世界" if orientation is Orientation.HORIZONTAL else "警告、「猫」。"
    viewports = [Viewport(320, 240), Viewport(640, 384), Viewport(800, 600)]

    masks = [_mask(text, orientation, viewport) for viewport in viewports]
    occupied = [np.count_nonzero(mask.alpha) for mask in masks]

    assert occupied[0] < occupied[1] < occupied[2]
    for mask in masks:
        _assert_ink_inside_margin(mask, 0.08)
