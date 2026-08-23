from __future__ import annotations

import hashlib
from dataclasses import FrozenInstanceError

import pytest

from mojit.application.request import PreparedRun
from mojit.core.models import Orientation


def _request(**changes: object) -> PreparedRun:
    data = b"font"
    values: dict[str, object] = {
        "text": "猫",
        "effect_id": "neon",
        "orientation": Orientation.HORIZONTAL,
        "font_data": data,
        "font_fingerprint": hashlib.sha256(data).hexdigest(),
        "fps": 30,
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
        request.fps = 60  # type: ignore[misc]


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
        ("margin", 0.5),
        ("seed", 2**63),
        ("debug", 1),
    ],
)
def test_prepared_run_rejects_invalid_state(field: str, value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        _request(**{field: value})
