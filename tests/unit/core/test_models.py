from __future__ import annotations

from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from mojit.core.models import (
    Frame,
    ModelValidationError,
    Orientation,
    RenderContext,
    TextMask,
    Viewport,
)


def test_viewport_is_a_validated_immutable_value() -> None:
    viewport = Viewport(width_px=np.int64(640), height_px=480)

    assert viewport == Viewport(640, 480)
    assert hash(viewport) == hash(Viewport(640, 480))
    with pytest.raises(FrozenInstanceError):
        viewport.width_px = 1  # type: ignore[misc]


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "1"])
def test_viewport_rejects_invalid_dimensions(value: object) -> None:
    with pytest.raises(ModelValidationError):
        Viewport(width_px=value, height_px=1)  # type: ignore[arg-type]


def test_text_mask_copies_and_irrevocably_freezes_its_buffer() -> None:
    source = np.arange(24, dtype=np.uint8).reshape(3, 8)[:, ::2]
    mask = TextMask(width=4, height=3, alpha=source)

    source[:] = 0

    assert mask.alpha[0, 1] == 2
    assert mask.alpha.flags.c_contiguous
    assert not np.shares_memory(mask.alpha, source)
    assert not mask.alpha.flags.writeable
    with pytest.raises(ValueError):
        mask.alpha.setflags(write=True)
    with pytest.raises(TypeError):
        hash(mask)


@pytest.mark.parametrize(
    ("array", "message"),
    [
        (np.zeros((2, 2), dtype=np.float32), "dtype"),
        (np.zeros((3, 2), dtype=np.uint8), "shape"),
        ([[0, 0], [0, 0]], "numpy.ndarray"),
    ],
)
def test_text_mask_rejects_invalid_array_contract(array: object, message: str) -> None:
    with pytest.raises(ModelValidationError, match=message):
        TextMask(width=2, height=2, alpha=array)  # type: ignore[arg-type]


def test_frame_owns_an_immutable_rgba_buffer() -> None:
    source = np.zeros((2, 3, 4), dtype=np.uint8)
    frame = Frame(width=3, height=2, rgba=source)
    source[0, 0] = 255

    assert np.count_nonzero(frame.rgba) == 0
    assert frame.rgba.shape == (2, 3, 4)
    assert not frame.rgba.flags.writeable
    with pytest.raises(ValueError):
        frame.rgba.setflags(write=True)


def test_frame_reuses_provably_immutable_bytes_backed_storage() -> None:
    source = np.frombuffer(bytes(range(24)), dtype=np.uint8).reshape((2, 3, 4))

    frame = Frame(width=3, height=2, rgba=source)

    assert np.shares_memory(frame.rgba, source)
    assert not frame.rgba.flags.writeable
    with pytest.raises(ValueError):
        frame.rgba.setflags(write=True)


def test_render_context_validates_deterministic_inputs() -> None:
    viewport = Viewport(100, 50)
    context = RenderContext(viewport=viewport, frame_index=3, elapsed_seconds=0.1)

    assert context.viewport is viewport
    assert context.frame_index == 3
    assert context.elapsed_seconds == 0.1
    assert Orientation.HORIZONTAL.value == "horizontal"


@pytest.mark.parametrize(
    ("frame_index", "elapsed"),
    [(-1, 0.0), (True, 0.0), (0, -0.1), (0, float("nan")), (0, float("inf"))],
)
def test_render_context_rejects_invalid_time_inputs(
    frame_index: object,
    elapsed: object,
) -> None:
    with pytest.raises(ModelValidationError):
        RenderContext(  # type: ignore[arg-type]
            viewport=Viewport(1, 1),
            frame_index=frame_index,
            elapsed_seconds=elapsed,
        )


def test_render_context_rejects_non_viewport_and_non_real_time() -> None:
    with pytest.raises(ModelValidationError, match="viewport"):
        RenderContext(viewport=(1, 1), frame_index=0, elapsed_seconds=0.0)  # type: ignore[arg-type]
    with pytest.raises(ModelValidationError, match="real number"):
        RenderContext(viewport=Viewport(1, 1), frame_index=0, elapsed_seconds="0")  # type: ignore[arg-type]
