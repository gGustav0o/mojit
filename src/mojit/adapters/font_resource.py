"""Filesystem boundary for loading and identifying a font resource."""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass, field
from pathlib import Path

from PIL import ImageFont


class FontResourceError(ValueError):
    """A font resource cannot be loaded or validated."""


@dataclass(frozen=True, slots=True)
class FontResource:
    """Immutable in-memory font with content-based identity."""

    source: Path = field(compare=False)
    data: bytes = field(repr=False, compare=False)
    fingerprint: str


def load_font_resource(path: str | Path) -> FontResource:
    """Read and validate one explicit font file."""
    if isinstance(path, str) and not path.strip():
        raise FontResourceError("font path must not be empty")
    if not isinstance(path, (str, Path)):
        raise FontResourceError("font path must be a string or Path")

    candidate = Path(path).expanduser()
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise FontResourceError(f"font file does not exist: {candidate}") from error
    if not resolved.is_file():
        raise FontResourceError(f"font path is not a file: {resolved}")

    try:
        data = resolved.read_bytes()
    except OSError as error:
        raise FontResourceError(f"font file is not readable: {resolved}") from error
    if not data:
        raise FontResourceError(f"font file is empty: {resolved}")

    try:
        ImageFont.truetype(io.BytesIO(data), size=1)
    except (OSError, ValueError) as error:
        raise FontResourceError(f"unsupported or invalid font file: {resolved}") from error

    fingerprint = hashlib.sha256(data).hexdigest()
    return FontResource(source=resolved, data=data, fingerprint=fingerprint)
