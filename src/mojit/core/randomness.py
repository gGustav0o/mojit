"""Stable derivation of effect-local deterministic random generators."""

from __future__ import annotations

import hashlib

import numpy as np

from mojit.core.models import ModelValidationError, require_int

_PERSONALIZATION = b"mojit-rng-v1"


def _field(value: bytes) -> bytes:
    return len(value).to_bytes(8, byteorder="big", signed=False) + value


def derive_random_seed(seed: int, effect_id: str, frame_index: int) -> int:
    """Derive a stable 128-bit seed without Python's randomized hash()."""
    normalized_seed = require_int(seed, name="seed", minimum=-(2**63))
    normalized_frame = require_int(frame_index, name="frame_index", minimum=0)
    if normalized_seed >= 2**63:
        raise ModelValidationError("seed must be < 2**63")
    if not isinstance(effect_id, str) or not effect_id:
        raise ModelValidationError("effect_id must be a non-empty string")

    payload = b"".join(
        (
            _field(str(normalized_seed).encode("ascii")),
            _field(effect_id.encode("utf-8")),
            _field(str(normalized_frame).encode("ascii")),
        )
    )
    digest = hashlib.blake2b(payload, digest_size=16, person=_PERSONALIZATION).digest()
    return int.from_bytes(digest, byteorder="big", signed=False)


def make_rng(seed: int, effect_id: str, frame_index: int) -> np.random.Generator:
    """Create a fresh, local PCG64 generator for one effect frame."""
    derived_seed = derive_random_seed(seed, effect_id, frame_index)
    return np.random.Generator(np.random.PCG64(derived_seed))
