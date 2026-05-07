"""ETag store contract tests — InMemoryETagStore + RedisETagStore.

Scope: invariants of the abstraction layer. Real ETag traffic against
CIMA is exercised end-to-end by the existing smoke / route tests.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock

from app.etag_store import (
    DEFAULT_MAX_ENTRIES,
    InMemoryETagStore,
    RedisETagStore,
)


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# InMemoryETagStore
# ---------------------------------------------------------------------------


def test_in_memory_get_returns_none_for_unknown_key() -> None:
    store = InMemoryETagStore()
    assert _run(store.get("nope")) is None


def test_in_memory_set_and_get_round_trip() -> None:
    store = InMemoryETagStore()
    payload = {"foo": "bar", "n": 1}

    async def go():
        await store.set("k", "etag-1", payload)
        return await store.get("k")

    assert _run(go()) == ("etag-1", payload)


def test_in_memory_set_overwrites_existing_key() -> None:
    store = InMemoryETagStore()

    async def go():
        await store.set("k", "etag-1", {"v": 1})
        await store.set("k", "etag-2", {"v": 2})
        return await store.get("k")

    assert _run(go()) == ("etag-2", {"v": 2})


def test_in_memory_lru_evicts_oldest_first() -> None:
    """When the store hits ``max_entries`` the LRU entry is dropped on
    the next ``set``. ``get`` is also a 'touch' — it bumps the entry to
    the most-recently-used end so a hot key never gets evicted."""
    store = InMemoryETagStore(max_entries=3)

    async def go():
        await store.set("a", "ea", "A")
        await store.set("b", "eb", "B")
        await store.set("c", "ec", "C")
        # touch 'a' so it becomes MRU
        await store.get("a")
        # 'b' is now LRU; the next set evicts it.
        await store.set("d", "ed", "D")
        return (
            await store.get("a"),
            await store.get("b"),
            await store.get("c"),
            await store.get("d"),
        )

    a, b, c, d = _run(go())
    assert a == ("ea", "A")
    assert b is None  # evicted
    assert c == ("ec", "C")
    assert d == ("ed", "D")


def test_in_memory_default_capacity_matches_module_constant() -> None:
    store = InMemoryETagStore()

    async def fill():
        for i in range(DEFAULT_MAX_ENTRIES + 1):
            await store.set(f"k{i}", f"e{i}", i)

    _run(fill())
    assert len(store) == DEFAULT_MAX_ENTRIES


# ---------------------------------------------------------------------------
# RedisETagStore
# ---------------------------------------------------------------------------


def test_redis_get_returns_none_when_key_missing() -> None:
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    store = RedisETagStore(redis)
    assert _run(store.get("k")) is None


def test_redis_get_decodes_stored_json_payload() -> None:
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=json.dumps({"etag": "etag-1", "payload": {"v": 1}}))
    store = RedisETagStore(redis)
    assert _run(store.get("k")) == ("etag-1", {"v": 1})


def test_redis_set_writes_with_ttl() -> None:
    redis = AsyncMock()
    redis.set = AsyncMock()
    store = RedisETagStore(redis)
    _run(store.set("k", "etag-1", {"v": 1}))
    redis.set.assert_awaited_once()
    args, kwargs = redis.set.call_args
    assert args[0] == "mcp-aemps:etag:k"
    body = json.loads(args[1])
    assert body == {"etag": "etag-1", "payload": {"v": 1}}
    assert kwargs.get("ex") and kwargs["ex"] > 0


def test_redis_get_swallows_connection_errors() -> None:
    redis = AsyncMock()
    redis.get = AsyncMock(side_effect=ConnectionError("boom"))
    store = RedisETagStore(redis)
    # Must not raise — best-effort contract.
    assert _run(store.get("k")) is None


def test_redis_set_swallows_connection_errors() -> None:
    redis = AsyncMock()
    redis.set = AsyncMock(side_effect=ConnectionError("boom"))
    store = RedisETagStore(redis)
    _run(store.set("k", "etag-1", {"v": 1}))  # must not raise


def test_redis_get_handles_corrupted_json() -> None:
    redis = AsyncMock()
    redis.get = AsyncMock(return_value="not-json")
    store = RedisETagStore(redis)
    assert _run(store.get("k")) is None
