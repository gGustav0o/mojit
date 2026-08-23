"""Pure validated Kitty Graphics Protocol command encoding."""

from __future__ import annotations

import base64
from collections.abc import Iterator

from mojit.adapters.wezterm.errors import KittyProtocolError

ESC = b"\x1b"
ST = ESC + b"\\"
DEFAULT_CHUNK_SIZE = 4096
MAX_IMAGE_ID = 2**31 - 1
_IMAGE_NAMESPACE = 0x4D000000
_PID_MASK = 0x00FFFFFF


def _require_int(
    value: object,
    *,
    name: str,
    minimum: int = 1,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise KittyProtocolError(f"{name} must be an integer")
    if value < minimum or (maximum is not None and value > maximum):
        upper = f" and <= {maximum}" if maximum is not None else ""
        raise KittyProtocolError(f"{name} must be >= {minimum}{upper}")
    return value


def make_image_id(process_id: int) -> int:
    """Derive one stable positive 31-bit ID from a process identifier."""
    pid = _require_int(process_id, name="process_id", minimum=0)
    return _IMAGE_NAMESPACE | (pid & _PID_MASK)


def _iter_transmit_commands(
    payload: bytes,
    *,
    image_id: int,
    width: int,
    height: int,
    columns: int,
    rows: int,
    encoded_chunk_size: int,
) -> Iterator[bytes]:
    raw_chunk_size = encoded_chunk_size // 4 * 3
    controls = (
        b"a=T",
        b"f=100",
        f"i={image_id}".encode("ascii"),
        b"q=1",
        b"C=1",
        f"s={width}".encode("ascii"),
        f"v={height}".encode("ascii"),
        f"c={columns}".encode("ascii"),
        f"r={rows}".encode("ascii"),
    )
    view = memoryview(payload)
    for offset in range(0, len(payload), raw_chunk_size):
        end = min(len(payload), offset + raw_chunk_size)
        encoded = base64.b64encode(view[offset:end])
        more = end < len(payload)
        chunk_controls = (
            (*controls, f"m={int(more)}".encode("ascii"))
            if offset == 0
            else (f"m={int(more)}".encode("ascii"),)
        )
        yield ESC + b"_G" + b",".join(chunk_controls) + b";" + encoded + ST


def iter_transmit_png(
    payload: bytes,
    *,
    image_id: int,
    width: int,
    height: int,
    columns: int,
    rows: int,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> Iterator[bytes]:
    """Return bounded Kitty transmission chunks for one complete PNG payload."""
    if not isinstance(payload, bytes) or not payload:
        raise KittyProtocolError("payload must be non-empty bytes")
    validated_id = _require_int(
        image_id,
        name="image_id",
        maximum=MAX_IMAGE_ID,
    )
    validated_width = _require_int(width, name="width")
    validated_height = _require_int(height, name="height")
    validated_columns = _require_int(columns, name="columns")
    validated_rows = _require_int(rows, name="rows")
    validated_chunk_size = _require_int(chunk_size, name="chunk_size", minimum=4)
    if validated_chunk_size % 4 != 0:
        raise KittyProtocolError("chunk_size must be a multiple of four")
    return _iter_transmit_commands(
        payload,
        image_id=validated_id,
        width=validated_width,
        height=validated_height,
        columns=validated_columns,
        rows=validated_rows,
        encoded_chunk_size=validated_chunk_size,
    )


def delete_image(image_id: int) -> bytes:
    """Delete one owned image and all of its placements."""
    validated_id = _require_int(
        image_id,
        name="image_id",
        maximum=MAX_IMAGE_ID,
    )
    return ESC + f"_Ga=d,d=I,i={validated_id},q=1".encode("ascii") + ST
