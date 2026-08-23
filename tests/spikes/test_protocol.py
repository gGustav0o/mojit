"""Regression tests for the decisions encoded by the Phase 0 protocol probe."""

from __future__ import annotations

import base64

from spikes.wezterm.protocol import ESC, ST, kitty_delete, kitty_image, restore_terminal


def _commands(stream: bytes) -> list[bytes]:
    return [ESC + b"_G" + part + ST for part in stream.split(ST) if part]


def test_kitty_image_chunks_payload_and_reuses_owned_id() -> None:
    payload = bytes(range(256)) * 40

    stream = kitty_image(
        payload,
        image_id=0x4D4F4A,
        image_format=100,
        width=80,
        height=24,
        compressed=False,
        columns=10,
        rows=3,
        chunk_size=4096,
    )
    commands = _commands(stream)
    controls_and_payload = [
        command.removeprefix(ESC + b"_G").removesuffix(ST) for command in commands
    ]
    encoded = b"".join(item.split(b";", maxsplit=1)[1] for item in controls_and_payload)

    assert base64.b64decode(encoded) == payload
    assert b"a=T,f=100,i=5066570,q=1,C=1,s=80,v=24,c=10,r=3,m=1" in commands[0]
    assert all(len(item.split(b";", maxsplit=1)[1]) <= 4096 for item in controls_and_payload)
    assert b"m=0" in commands[-1]


def test_restore_is_stable_and_deletes_only_owned_image() -> None:
    image_id = 0x4D4F4A

    first = restore_terminal(image_id)
    second = restore_terminal(image_id)

    assert first == second
    assert kitty_delete(image_id) in first
    assert first.endswith(ESC + b"[?25h" + ESC + b"[?1049l")
