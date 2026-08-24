from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from mojit.core.models import ModelValidationError, Orientation, Viewport
from mojit.core.typography import (
    FontDataError,
    InvalidTextError,
    ShapingUnavailableError,
    TypographyKey,
    rasterize_text_mask,
    require_shaping_capability,
)

FINGERPRINT = "a" * 64


def _key() -> TypographyKey:
    return TypographyKey(
        text="電脳世界",
        font_fingerprint=FINGERPRINT,
        orientation=Orientation.HORIZONTAL,
        viewport=Viewport(640, 480),
        margin=0.08,
    )


def test_typography_key_is_the_complete_cache_identity() -> None:
    baseline = _key()
    variants = [
        replace(baseline, text="猫"),
        replace(baseline, font_fingerprint="b" * 64),
        replace(baseline, orientation=Orientation.VERTICAL),
        replace(baseline, viewport=Viewport(800, 600)),
        replace(baseline, margin=0.1),
        replace(baseline, language="en"),
        replace(baseline, features=("-kern",)),
    ]

    assert baseline.direction == "ltr"
    assert replace(baseline, orientation=Orientation.VERTICAL).direction == "ttb"
    assert len({baseline, *variants}) == len(variants) + 1


def test_features_are_normalized_to_an_immutable_tuple() -> None:
    key = replace(_key(), features=["-kern"])  # type: ignore[arg-type]

    assert key.features == ("-kern",)


@pytest.mark.parametrize("text", ["", " ", "\t\r\n", "a\nb", "a\rb", "a\0b"])
def test_typography_key_rejects_invalid_text(text: str) -> None:
    with pytest.raises(InvalidTextError):
        replace(_key(), text=text)


@pytest.mark.parametrize("fingerprint", ["", "A" * 64, "0" * 63, "x" * 64])
def test_typography_key_rejects_invalid_font_identity(fingerprint: str) -> None:
    with pytest.raises(FontDataError):
        replace(_key(), font_fingerprint=fingerprint)


def test_typography_key_rejects_non_orientation() -> None:
    with pytest.raises(ModelValidationError):
        replace(_key(), orientation="horizontal")  # type: ignore[arg-type]


def test_typography_key_rejects_invalid_viewport_and_language() -> None:
    with pytest.raises(ModelValidationError, match="viewport"):
        replace(_key(), viewport=(640, 480))  # type: ignore[arg-type]
    with pytest.raises(ModelValidationError, match="language"):
        replace(_key(), language="  ")


@pytest.mark.parametrize("features", [None, "-kern", ("",), (1,)])
def test_typography_key_rejects_invalid_features(features: object) -> None:
    with pytest.raises(ModelValidationError):
        replace(_key(), features=features)  # type: ignore[arg-type]


def test_rasterizer_rejects_empty_or_mismatched_font_data_before_shaping() -> None:
    with pytest.raises(FontDataError, match="non-empty"):
        rasterize_text_mask(b"", _key())
    with pytest.raises(FontDataError, match="does not match"):
        rasterize_text_mask(b"not a font", _key())


def test_rasterizer_reports_missing_shaping_capability(monkeypatch: pytest.MonkeyPatch) -> None:
    font_data = b"identity-only"
    key = replace(_key(), font_fingerprint=hashlib.sha256(font_data).hexdigest())
    monkeypatch.setattr("mojit.core.typography.pil_features.check_feature", lambda _: False)

    with pytest.raises(ShapingUnavailableError, match="FriBiDi"):
        rasterize_text_mask(font_data, key)


def test_public_shaping_preflight_reports_missing_raqm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("mojit.core.typography.pil_features.check_feature", lambda _: False)

    with pytest.raises(ShapingUnavailableError, match="Raqm/FriBiDi"):
        require_shaping_capability()


def test_public_shaping_preflight_accepts_raqm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("mojit.core.typography.pil_features.check_feature", lambda _: True)

    require_shaping_capability()


def test_rasterizer_maps_invalid_matching_font_data(monkeypatch: pytest.MonkeyPatch) -> None:
    font_data = b"not a font"
    key = replace(_key(), font_fingerprint=hashlib.sha256(font_data).hexdigest())
    monkeypatch.setattr("mojit.core.typography.pil_features.check_feature", lambda _: True)

    with pytest.raises(FontDataError, match="Pillow/FreeType"):
        rasterize_text_mask(font_data, key)
