"""Application-owned bounded TextMask cache and invalidation rules."""

from __future__ import annotations

from collections.abc import Callable

from mojit.core.models import TextMask
from mojit.core.typography import TypographyKey


class MaskCacheContractError(ValueError):
    """A cache key or factory result violates the mask contract."""


class TextMaskCache:
    """Retain only the mask for the currently active typography key."""

    __slots__ = ("_entry",)

    def __init__(self) -> None:
        self._entry: tuple[TypographyKey, TextMask] | None = None

    def __len__(self) -> int:
        return int(self._entry is not None)

    def get_or_create(
        self,
        key: TypographyKey,
        factory: Callable[[], TextMask],
    ) -> TextMask:
        """Return a cached mask or atomically replace the entry after a valid miss."""
        if not isinstance(key, TypographyKey):
            raise TypeError("key must be a TypographyKey")
        if not callable(factory):
            raise TypeError("factory must be callable")

        if self._entry is not None and self._entry[0] == key:
            return self._entry[1]

        mask = factory()
        if not isinstance(mask, TextMask):
            raise MaskCacheContractError("factory must return a TextMask")
        expected_dimensions = (key.viewport.width_px, key.viewport.height_px)
        if (mask.width, mask.height) != expected_dimensions:
            raise MaskCacheContractError(
                "factory mask dimensions must match the typography-key viewport"
            )

        self._entry = (key, mask)
        return mask

    def clear(self) -> None:
        """Release the current key and mask."""
        self._entry = None
