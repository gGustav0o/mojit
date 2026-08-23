from __future__ import annotations

import numpy as np
import pytest

from mojit.application.mask_cache import MaskCacheContractError, TextMaskCache
from mojit.core.models import Orientation, TextMask, Viewport
from mojit.core.typography import TypographyKey


def _key(width: int = 8, height: int = 6) -> TypographyKey:
    return TypographyKey(
        text="猫",
        font_fingerprint="0" * 64,
        orientation=Orientation.HORIZONTAL,
        viewport=Viewport(width, height),
        margin=0.08,
    )


def _mask(width: int = 8, height: int = 6, value: int = 0) -> TextMask:
    return TextMask(width, height, np.full((height, width), value, dtype=np.uint8))


def test_cache_starts_empty_and_clear_releases_entry() -> None:
    cache = TextMaskCache()
    assert len(cache) == 0

    cache.get_or_create(_key(), _mask)
    assert len(cache) == 1

    cache.clear()
    assert len(cache) == 0


def test_equal_key_returns_exact_cached_object_without_calling_factory() -> None:
    cache = TextMaskCache()
    first = _mask(value=17)
    assert cache.get_or_create(_key(), lambda: first) is first

    def unexpected_factory() -> TextMask:
        raise AssertionError("cache hit must not call factory")

    assert cache.get_or_create(_key(), unexpected_factory) is first


def test_each_key_change_replaces_the_single_entry() -> None:
    cache = TextMaskCache()
    calls: list[tuple[int, int]] = []

    def create(width: int, height: int) -> TextMask:
        calls.append((width, height))
        return _mask(width, height)

    cache.get_or_create(_key(8, 6), lambda: create(8, 6))
    cache.get_or_create(_key(10, 7), lambda: create(10, 7))
    cache.get_or_create(_key(8, 6), lambda: create(8, 6))

    assert calls == [(8, 6), (10, 7), (8, 6)]
    assert len(cache) == 1


@pytest.mark.parametrize(
    "factory",
    [
        lambda: object(),
        lambda: _mask(7, 6),
        lambda: _mask(8, 5),
    ],
)
def test_invalid_factory_result_does_not_replace_valid_entry(factory: object) -> None:
    cache = TextMaskCache()
    original_key = _key()
    original = _mask(value=51)
    cache.get_or_create(original_key, lambda: original)

    with pytest.raises(MaskCacheContractError):
        cache.get_or_create(_key(9, 7), factory)  # type: ignore[arg-type]

    assert cache.get_or_create(original_key, lambda: _mask(value=99)) is original


def test_factory_exception_does_not_replace_valid_entry() -> None:
    cache = TextMaskCache()
    original_key = _key()
    original = _mask(value=51)
    cache.get_or_create(original_key, lambda: original)

    def fail() -> TextMask:
        raise RuntimeError("rasterization failed")

    with pytest.raises(RuntimeError, match="rasterization failed"):
        cache.get_or_create(_key(9, 7), fail)

    assert cache.get_or_create(original_key, fail) is original


@pytest.mark.parametrize(
    ("key", "factory", "message"),
    [
        (object(), _mask, "key must be"),
        (_key(), object(), "factory must be"),
    ],
)
def test_cache_rejects_invalid_arguments(key: object, factory: object, message: str) -> None:
    with pytest.raises(TypeError, match=message):
        TextMaskCache().get_or_create(key, factory)  # type: ignore[arg-type]
