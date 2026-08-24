from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest
from PIL import features as pil_features

from mojit.adapters.budoux_segmenter import segment_japanese_phrases
from mojit.adapters.font_resource import load_font_resource
from mojit.core.models import Orientation, RenderContext, TextMask, Viewport
from mojit.core.typography import TypographyKey, rasterize_text_mask
from mojit.effects.api import EffectConfig
from mojit.effects.registry import get_effect

REFERENCE_FONT = Path("C:/Windows/Fonts/YuGothB.ttc")
REFERENCE_FONT_SHA256 = "d923a57f781f06198167da4f58287be7ac64a954a47aff4295e078a42b4b68b2"
REFERENCE_FRAME_SHA256 = {
    (Orientation.HORIZONTAL, "chromatic"): (
        "059286d5b64ce18ac1ae02238c1462c42bc6158015bc8df7d266fb00761f9bce"
    ),
    (Orientation.HORIZONTAL, "glitch"): (
        "7259d422d4a7d2b73771f9cc9a0896d3e5a170ad511af71ca589d2ee6d9cdeac"
    ),
    (Orientation.HORIZONTAL, "neon"): (
        "d99852907bbea94860114370ce3c234a57c24b57c69a452404c58343d3a11e3e"
    ),
    (Orientation.HORIZONTAL, "pulse"): (
        "a38586dd35d2a1cdac54a0cdbbd1a00d349654ebd1cfb810eb99ed1e0e613c1d"
    ),
    (Orientation.VERTICAL, "chromatic"): (
        "ffc6e6847c15da24e902af1c9ffdd98c5542c1e3d35f5eebb8ccd28c555d4af2"
    ),
    (Orientation.VERTICAL, "glitch"): (
        "1f80dd42eec1d78bbf84b8851dddeae9671551db8ba517b68c646ecb50312fb3"
    ),
    (Orientation.VERTICAL, "neon"): (
        "f6791a63d143880319303462e5faaed99a25d2193eb8cd725291aced4eb9f58a"
    ),
    (Orientation.VERTICAL, "pulse"): (
        "021b770855889dc0cde1ff94d6f158812fd4be42899dc71060eb03fa72c956a0"
    ),
}


@pytest.fixture(scope="module")
def reference_masks() -> dict[Orientation, TextMask]:
    if not REFERENCE_FONT.is_file():
        pytest.skip(f"reference font is absent: {REFERENCE_FONT}")
    if not pil_features.check_feature("raqm"):
        pytest.skip("Pillow Raqm/FriBiDi capability is unavailable")
    resource = load_font_resource(REFERENCE_FONT)
    if resource.fingerprint != REFERENCE_FONT_SHA256:
        pytest.skip("reference font checksum differs from the Phase 0 baseline")

    viewport = Viewport(640, 384)
    return {
        orientation: rasterize_text_mask(
            resource.data,
            TypographyKey(
                text="電脳世界" if orientation is Orientation.HORIZONTAL else "警告、「猫」。",
                font_fingerprint=resource.fingerprint,
                orientation=orientation,
                viewport=viewport,
                margin=0.08,
            ),
            phrases=(
                segment_japanese_phrases("電脳世界")
                if orientation is Orientation.HORIZONTAL
                else ("警告、「猫」。",)
            ),
        )
        for orientation in Orientation
    }


@pytest.mark.typography_reference
@pytest.mark.parametrize("orientation", list(Orientation))
@pytest.mark.parametrize("effect_id", ["chromatic", "glitch", "neon", "pulse"])
def test_effect_reference_frames_are_stable_and_unclipped(
    reference_masks: dict[Orientation, TextMask],
    orientation: Orientation,
    effect_id: str,
) -> None:
    mask = reference_masks[orientation]
    context = RenderContext(Viewport(mask.width, mask.height), 17, 17 / 30)
    frame = get_effect(effect_id)(mask, context, EffectConfig(42))

    assert (
        hashlib.sha256(frame.rgba.tobytes()).hexdigest()
        == REFERENCE_FRAME_SHA256[orientation, effect_id]
    )
    border_alpha = np.concatenate(
        (frame.rgba[0, :, 3], frame.rgba[-1, :, 3], frame.rgba[:, 0, 3], frame.rgba[:, -1, 3])
    )
    assert np.count_nonzero(border_alpha) == 0
