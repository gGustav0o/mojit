from __future__ import annotations

import base64
import hashlib
import io

import numpy as np
from PIL import Image

from mojit.adapters.wezterm.backend import WezTermBackend
from mojit.adapters.wezterm.kitty_protocol import ESC, ST
from mojit.adapters.wezterm.terminal_state import ENTER_TERMINAL, LEAVE_ALTERNATE_SCREEN
from mojit.adapters.wezterm.viewport import PaneGeometry
from mojit.application.request import PreparedRun
from mojit.application.runtime import run_animation
from mojit.core.models import Frame, Orientation, TextMask, Viewport
from mojit.core.typography import TypographyKey


def _geometry(
    width: int,
    height: int,
    *,
    columns: int = 80,
    rows: int = 24,
) -> PaneGeometry:
    return PaneGeometry(2, Viewport(width, height), columns, rows, 96.0)


def _transmit_payload(terminal_bytes: bytes) -> tuple[list[bytes], bytes]:
    controls: list[bytes] = []
    chunks: list[bytes] = []
    offset = 0
    while True:
        start = terminal_bytes.find(ESC + b"_G", offset)
        if start < 0:
            break
        end = terminal_bytes.index(ST, start)
        command = terminal_bytes[start + len(ESC + b"_G") : end]
        offset = end + len(ST)
        control, separator, payload = command.partition(b";")
        if b"a=T" in control:
            assert separator == b";"
            controls.append(control)
            chunks.append(payload)
    return controls, base64.b64decode(b"".join(chunks), validate=True)


def test_frame_round_trips_through_png_kitty_and_terminal_lifecycle() -> None:
    rgba = np.array(
        [
            [[255, 0, 0, 255], [0, 255, 0, 128]],
            [[0, 0, 255, 64], [255, 255, 255, 0]],
        ],
        dtype=np.uint8,
    )
    frame = Frame(2, 2, rgba)
    output = io.BytesIO()
    backend = WezTermBackend(
        pane_id=2,
        output=output,
        image_id=123,
        query_geometry=lambda pane_id: _geometry(2, 2, columns=2, rows=2),
    )

    backend.preflight()
    backend.enter()
    assert backend.get_viewport() == Viewport(2, 2)
    backend.present(frame)
    backend.restore()

    terminal_bytes = output.getvalue()
    controls, png = _transmit_payload(terminal_bytes)
    with Image.open(io.BytesIO(png)) as image:
        decoded = np.array(image.convert("RGBA"), dtype=np.uint8)

    assert np.array_equal(decoded, rgba)
    assert len(controls) == 1
    assert b"i=123" in controls[0]
    assert b"s=2,v=2,c=2,r=2" in controls[0]
    assert terminal_bytes.startswith(ENTER_TERMINAL)
    assert terminal_bytes.endswith(LEAVE_ALTERNATE_SCREEN)
    assert b"a=d,d=I,i=123" in terminal_bytes
    assert output.closed is False


class AdvancingClock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def _request() -> PreparedRun:
    font_data = b"synthetic-font"
    return PreparedRun(
        text="猫",
        effect_id="pulse",
        orientation=Orientation.HORIZONTAL,
        font_data=font_data,
        font_fingerprint=hashlib.sha256(font_data).hexdigest(),
        fps=30,
        margin=0.08,
        seed=7,
    )


def _rasterize(font_data: bytes, key: TypographyKey) -> TextMask:
    alpha = np.full(
        (key.viewport.height_px, key.viewport.width_px),
        180,
        dtype=np.uint8,
    )
    return TextMask(key.viewport.width_px, key.viewport.height_px, alpha)


def test_runtime_drives_real_wezterm_backend_across_resize() -> None:
    geometries = [_geometry(24, 18), _geometry(28, 20, columns=90, rows=28)]
    query_count = 0

    def query(pane_id: int) -> PaneGeometry:
        nonlocal query_count
        geometry = geometries[min(query_count, len(geometries) - 1)]
        query_count += 1
        return geometry

    output = io.BytesIO()
    backend = WezTermBackend(
        pane_id=2,
        output=output,
        image_id=456,
        query_geometry=query,
    )
    presented = 0
    original_present = backend.present

    class CountingBackend:
        def get_viewport(self) -> Viewport | None:
            return backend.get_viewport()

        def present(self, frame: Frame) -> None:
            nonlocal presented
            original_present(frame)
            presented += 1

    backend.preflight()
    backend.enter()
    result = run_animation(
        _request(),
        backend=CountingBackend(),
        clock=AdvancingClock(),
        rasterizer=_rasterize,
        should_stop=lambda: presented == 17,
    )
    backend.restore()

    terminal_bytes = output.getvalue()
    assert result.presented_frames == 17
    assert result.viewport_changes == 1
    assert terminal_bytes.count(b"a=T") == 17
    assert b"s=28,v=20,c=90,r=28" in terminal_bytes
    assert terminal_bytes.endswith(LEAVE_ALTERNATE_SCREEN)
