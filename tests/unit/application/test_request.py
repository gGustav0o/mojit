from __future__ import annotations

import hashlib
from dataclasses import FrozenInstanceError

import pytest

from mojit.application.request import PreparedRun
from mojit.core.models import MAX_SCENE_LAYERS, Orientation


def _request(**changes: object) -> PreparedRun:
    data = b"font"
    values: dict[str, object] = {
        "text": "猫",
        "effect_id": "neon",
        "orientation": Orientation.HORIZONTAL,
        "font_data": data,
        "font_fingerprint": hashlib.sha256(data).hexdigest(),
        "fps": 8,
        "margin": 0.08,
        "seed": 0,
        "debug": False,
    }
    values.update(changes)
    return PreparedRun(**values)  # type: ignore[arg-type]


def test_prepared_run_is_frozen_and_normalizes_margin() -> None:
    request = _request(margin=0)
    assert request.margin == 0.0
    with pytest.raises(FrozenInstanceError):
        request.fps = 15  # type: ignore[misc]


@pytest.mark.parametrize("fps", [1, 15])
def test_prepared_run_accepts_fps_boundaries(fps: int) -> None:
    assert _request(fps=fps).fps == fps


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("text", ""),
        ("text", "a\nb"),
        ("text", "a" * 4097),
        ("effect_id", "Neon"),
        ("orientation", "horizontal"),
        ("font_data", b""),
        ("font_fingerprint", "0" * 64),
        ("fps", 0),
        ("fps", 16),
        ("margin", 0.5),
        ("seed", 2**63),
        ("debug", 1),
        ("scene_id", "Rainy Night"),
        ("scene_layers", ("stars",)),
        ("scene_layers", ("unknown", "text")),
    ],
)
def test_prepared_run_rejects_invalid_state(field: str, value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        _request(**{field: value})


def test_prepared_run_rejects_preset_and_custom_scene_together() -> None:
    with pytest.raises(ValueError, match="mutually exclusive"):
        _request(scene_id="space", scene_layers=("text",))


def test_prepared_run_rejects_a_custom_scene_above_the_layer_limit() -> None:
    with pytest.raises(ValueError, match=str(MAX_SCENE_LAYERS)):
        _request(scene_layers=("stars",) * MAX_SCENE_LAYERS + ("text",))
