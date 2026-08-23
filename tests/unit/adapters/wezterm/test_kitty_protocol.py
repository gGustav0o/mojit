from __future__ import annotations

import base64

import pytest

from mojit.adapters.wezterm.errors import KittyProtocolError
from mojit.adapters.wezterm.kitty_protocol import (
    ESC,
    ST,
    delete_image,
    iter_transmit_png,
    make_image_id,
)


def _encoded_payload(command: bytes) -> bytes:
    return command.removesuffix(ST).split(b";", 1)[1]


def test_process_image_id_is_stable_namespaced_and_positive() -> None:
    assert make_image_id(0) == 0x4D000000
    assert make_image_id(42) == 0x4D00002A
    assert make_image_id(0x12345678) == 0x4D345678
    assert make_image_id(42) == make_image_id(42)


@pytest.mark.parametrize("process_id", [True, -1, 1.5, "1"])
def test_process_image_id_rejects_invalid_pid(process_id: object) -> None:
    with pytest.raises(KittyProtocolError, match="process_id"):
        make_image_id(process_id)  # type: ignore[arg-type]


def test_single_chunk_transmission_has_exact_controls() -> None:
    payload = b"png"
    commands = list(
        iter_transmit_png(
            payload,
            image_id=17,
            width=640,
            height=480,
            columns=80,
            rows=24,
        )
    )
    assert commands == [
        ESC
        + b"_Ga=T,f=100,i=17,q=1,C=1,s=640,v=480,c=80,r=24,m=0;"
        + base64.b64encode(payload)
        + ST
    ]


def test_multiple_chunks_reconstruct_payload_and_limit_continuation_controls() -> None:
    payload = bytes(range(256)) * 40
    commands = list(
        iter_transmit_png(
            payload,
            image_id=19,
            width=10,
            height=11,
            columns=12,
            rows=13,
            chunk_size=16,
        )
    )

    assert len(commands) > 2
    assert b"a=T" in commands[0]
    assert b",m=1;" in commands[0]
    assert all(command.startswith(ESC + b"_Gm=") for command in commands[1:])
    assert commands[-1].startswith(ESC + b"_Gm=0;")
    encoded = b"".join(_encoded_payload(command) for command in commands)
    assert base64.b64decode(encoded, validate=True) == payload
    assert all(len(_encoded_payload(command)) <= 16 for command in commands)


@pytest.mark.parametrize(
    "changes",
    [
        {"payload": b""},
        {"payload": bytearray(b"png")},
        {"image_id": 0},
        {"image_id": 2**31},
        {"width": 0},
        {"height": True},
        {"columns": -1},
        {"rows": 1.5},
        {"chunk_size": 2},
        {"chunk_size": 10},
    ],
)
def test_transmission_rejects_invalid_values(changes: dict[str, object]) -> None:
    values: dict[str, object] = {
        "payload": b"png",
        "image_id": 17,
        "width": 10,
        "height": 11,
        "columns": 12,
        "rows": 13,
        "chunk_size": 16,
    }
    values.update(changes)
    with pytest.raises(KittyProtocolError):
        iter_transmit_png(**values)  # type: ignore[arg-type]


def test_delete_command_is_exact_and_quiet() -> None:
    assert delete_image(17) == ESC + b"_Ga=d,d=I,i=17,q=1" + ST


@pytest.mark.parametrize("image_id", [0, True, 2**31])
def test_delete_rejects_invalid_id(image_id: object) -> None:
    with pytest.raises(KittyProtocolError):
        delete_image(image_id)  # type: ignore[arg-type]
