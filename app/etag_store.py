# app/etag_store.py
"""Pluggable ETag store for the CIMA HTTP client.

CIMA's CDN sends ETag + ``Cache-Control: max-age=1800`` headers on most
endpoints. The client sends ``If-None-Match`` on revalidation; on
``304 Not Modified`` we reuse the cached parsed payload — that's where
the real saving comes from (zero JSON parsing, zero downstream
allocation, no rate-limit budget burnt).

Two implementations ship in Community:

* ``InMemoryETagStore`` — process-local LRU, the default. Adequate for
  single-instance deployments and dev.
* ``RedisETagStore`` — Redis / Valkey-backed. Active automatically
  when ``REDIS_URL`` is configured (same opt-in as the rest of the
  Redis surface). Multi-replica deployments share the ETag map so a
  304 against one replica benefits every other replica — the win
  scales linearly with replica count on hot endpoints.

The abstraction is the seam Premium / enterprise forks can target if
they want a backend that's not Redis (Memcached, Cloudflare Workers KV,
DynamoDB, …) without touching ``cima_client.py``.

Failure mode: every method is best-effort. Network errors, JSON
deserialisation errors and missing keys all return ``None`` from
``get()`` and silently drop ``set()`` writes. The CIMA client treats
the store as a hint, never a source of truth — losing the cache means
extra upstream load, not data corruption.
"""

from __future__ import annotations

import json
import logging
from collections import OrderedDict
from typing import Any, Protocol

logger = logging.getLogger(__name__)

DEFAULT_MAX_ENTRIES = 2048
REDIS_KEY_PREFIX = "mcp-aemps:etag:"
# CIMA's max-age=1800 + safety margin; revalidation will refresh anyway.
REDIS_TTL_SECONDS = 3600


class ETagStore(Protocol):
    """Read/write contract for the CIMA ETag cache.

    Methods are async to leave room for I/O-backed implementations
    without changing the call sites in ``cima_client._request``.
    """

    async def get(self, key: str) -> tuple[str, Any] | None: ...

    async def set(self, key: str, etag: str, payload: Any) -> None: ...


class InMemoryETagStore:
    """Process-local LRU. ``OrderedDict``-backed for O(1) eviction in
    insertion order; calling ``set`` on an existing key bumps it to the
    most-recently-used end so cold entries get evicted first under
    pressure."""

    def __init__(self, max_entries: int = DEFAULT_MAX_ENTRIES):
        self._store: "OrderedDict[str, tuple[str, Any]]" = OrderedDict()
        self._max = max_entries

    async def get(self, key: str) -> tuple[str, Any] | None:
        entry = self._store.get(key)
        if entry is not None:
            # Touch — moves the key to MRU end.
            self._store.move_to_end(key)
        return entry

    async def set(self, key: str, etag: str, payload: Any) -> None:
        if key in self._store:
            self._store.move_to_end(key)
        elif len(self._store) >= self._max:
            self._store.popitem(last=False)  # drop LRU
        self._store[key] = (etag, payload)

    def __len__(self) -> int:  # pragma: no cover - debug helper
        return len(self._store)


class RedisETagStore:
    """Redis / Valkey-backed ETag store. Stores ``{etag, payload}`` as
    JSON text under ``mcp-aemps:etag:<key>`` with a 1-hour TTL.

    ``payload`` is JSON-serialised with ``default=str`` so Pydantic
    models, dataclasses and datetime objects don't blow up — at the
    cost of a one-way coercion (datetimes become ISO strings, sets
    become lists). That's safe for the ETag use case: the cached
    payload is replayed verbatim into ``_request`` callers, which
    treat CIMA responses as JSON dicts already."""

    def __init__(self, redis: Any):
        self._redis = redis

    async def get(self, key: str) -> tuple[str, Any] | None:
        try:
            raw = await self._redis.get(REDIS_KEY_PREFIX + key)
        except Exception as exc:  # noqa: BLE001
            logger.debug("RedisETagStore.get failed (%s); skipping", type(exc).__name__)
            return None
        if not raw:
            return None
        try:
            data = json.loads(raw)
            return data["etag"], data["payload"]
        except (json.JSONDecodeError, KeyError, TypeError):
            return None

    async def set(self, key: str, etag: str, payload: Any) -> None:
        try:
            value = json.dumps({"etag": etag, "payload": payload}, default=str, ensure_ascii=False)
            await self._redis.set(
                REDIS_KEY_PREFIX + key,
                value,
                ex=REDIS_TTL_SECONDS,
            )
        except Exception as exc:  # noqa: BLE001
            # Best-effort: a failed write just means the next request
            # re-fetches from CIMA. Never raise.
            logger.debug("RedisETagStore.set failed (%s); skipping", type(exc).__name__)


# Module-global singleton. ``cima_client`` reads this at request time;
# the lifespan hook in ``app.lifespan`` swaps it for a Redis-backed
# instance once the cache backend is up. Stdio (no FastAPI lifespan)
# stays on the in-memory default.
_active_store: ETagStore = InMemoryETagStore()


def get_active_store() -> ETagStore:
    return _active_store


def set_active_store(store: ETagStore) -> None:
    """Swap the active store. Called from ``app.lifespan`` when a Redis
    backend has been confirmed reachable. Tests can also use this to
    inject a stub. Premium / enterprise forks call this from their own
    startup path with their custom backend."""
    global _active_store
    _active_store = store


__all__ = [
    "DEFAULT_MAX_ENTRIES",
    "ETagStore",
    "InMemoryETagStore",
    "RedisETagStore",
    "get_active_store",
    "set_active_store",
]
