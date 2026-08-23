"""Minimal protocol encoders used only by Phase 0 probes."""

from __future__ import annotations

import base64

ESC = b"\x1b"
ST = ESC + b"\\"


def kitty_image(
    payload: bytes,
    *,
    image_id: int,
    image_format: int,
    width: int,
    height: int,
    compressed: bool,
    columns: int | None = None,
    rows: int | None = None,
    chunk_size: int = 4096,
) -> bytes:
    encoded = base64.b64encode(payload)
    chunks = [encoded[index : index + chunk_size] for index in range(0, len(encoded), chunk_size)]
    if not chunks:
        chunks = [b""]

    controls = [
        b"a=T",
        f"f={image_format}".encode("ascii"),
        f"i={image_id}".encode("ascii"),
        b"q=1",
        b"C=1",
        f"s={width}".encode("ascii"),
        f"v={height}".encode("ascii"),
    ]
    if compressed:
        controls.append(b"o=z")
    if columns is not None:
        controls.append(f"c={columns}".encode("ascii"))
    if rows is not None:
        controls.append(f"r={rows}".encode("ascii"))

    output: list[bytes] = []
    for index, chunk in enumerate(chunks):
        more = index < len(chunks) - 1
        chunk_controls = (
            controls + [f"m={int(more)}".encode("ascii")]
            if index == 0
            else [f"m={int(more)}".encode("ascii")]
        )
        output.append(ESC + b"_G" + b",".join(chunk_controls) + b";" + chunk + ST)
    return b"".join(output)


def kitty_delete(image_id: int) -> bytes:
    return ESC + f"_Ga=d,d=I,i={image_id}".encode("ascii") + ST


def iterm_image(png: bytes) -> bytes:
    payload = base64.b64encode(png)
    header = b"]1337;File=inline=1;width=100%;height=100%;preserveAspectRatio=0;doNotMoveCursor=1:"
    return ESC + header + payload + b"\x07"


def enter_terminal() -> bytes:
    return ESC + b"[?1049h" + ESC + b"[2J" + ESC + b"[H" + ESC + b"[?25l"


def begin_synchronized_update() -> bytes:
    return ESC + b"[?2026h"


def end_synchronized_update() -> bytes:
    return ESC + b"[?2026l"


def restore_terminal(image_id: int) -> bytes:
    return end_synchronized_update() + kitty_delete(image_id) + ESC + b"[?25h" + ESC + b"[?1049l"
