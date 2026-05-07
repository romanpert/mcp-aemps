"""Direct unit tests for ``app.cima_client``.

Until v0.4.12 the client was only exercised indirectly through the
route + tool tests. The behaviours pinned here all have a history of
quietly regressing:

- ETag round-trip: ``If-None-Match`` sent on revalidation, 304 reuses
  the cached payload, fresh 200 stores the new ETag.
- 429 retry: single bounded retry honouring ``Retry-After`` (capped),
  with default + jitter when the header is absent.
- Shared client singleton: same instance across calls within one loop.

Network is mocked via httpx's MockTransport so the tests are hermetic
and run without internet.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from app import cima_client
from app.cima_client import _parse_retry_after


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _reset_shared_client():
    """Each test gets a fresh module state — no leaked AsyncClient
    between cases."""
    yield
    _run(cima_client.aclose_shared_client())


# ---------------------------------------------------------------------------
# Retry-After parser
# ---------------------------------------------------------------------------


def test_parse_retry_after_handles_seconds_int() -> None:
    assert _parse_retry_after("3") == 3.0


def test_parse_retry_after_handles_seconds_float() -> None:
    assert _parse_retry_after("0.5") == 0.5


def test_parse_retry_after_caps_long_delays() -> None:
    """Per the policy: anything longer than the cap means we should let
    the original 429 surface rather than block the request that long."""
    parsed = _parse_retry_after("3600")
    assert parsed is not None
    assert parsed <= 8.0


def test_parse_retry_after_returns_none_on_garbage() -> None:
    """HTTP-date format / negative numbers / empty / None / unparseable —
    fall through to the default delay."""
    assert _parse_retry_after(None) is None
    assert _parse_retry_after("") is None
    assert _parse_retry_after("Wed, 21 Oct 2026 07:28:00 GMT") is None
    assert _parse_retry_after("-5") is None


# ---------------------------------------------------------------------------
# Shared httpx client invariants
# ---------------------------------------------------------------------------


def test_shared_client_is_singleton() -> None:
    """v0.4.11 perf fix: every CIMA call must share the same
    AsyncClient so the connection pool actually pools."""

    async def go():
        a = await cima_client._get_shared_client()
        b = await cima_client._get_shared_client()
        assert a is b

    _run(go())


# ---------------------------------------------------------------------------
# ETag round-trip
# ---------------------------------------------------------------------------


def test_etag_revalidation_round_trip() -> None:
    """First call: store the ETag. Second call: send If-None-Match;
    304 → reuse cached payload without re-parsing."""
    from app.etag_store import InMemoryETagStore, set_active_store

    set_active_store(InMemoryETagStore())

    requests_seen: list[dict] = []
    responses = [
        httpx.Response(
            200,
            headers={"ETag": '"v1"', "Content-Type": "application/json"},
            json={"resultados": [{"nregistro": "12345"}]},
        ),
        httpx.Response(304, headers={"ETag": '"v1"'}),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        requests_seen.append(
            {"path": request.url.path, "if_none_match": request.headers.get("If-None-Match")}
        )
        return responses[len(requests_seen) - 1]

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)

    async def go():
        try:
            r1 = await cima_client._request("GET", "medicamentos", params={"nombre": "x"}, client=client)
            r2 = await cima_client._request("GET", "medicamentos", params={"nombre": "x"}, client=client)
            return r1, r2
        finally:
            await client.aclose()

    r1, r2 = _run(go())

    # First call: no If-None-Match (cache cold), 200 with payload.
    assert requests_seen[0]["if_none_match"] is None
    assert r1 == {"resultados": [{"nregistro": "12345"}]}

    # Second call: ETag sent, 304 received, payload re-served from cache.
    assert requests_seen[1]["if_none_match"] == '"v1"'
    assert r2 == {"resultados": [{"nregistro": "12345"}]}
    assert r2 == r1, "304 path must return the same payload as the original 200"


# ---------------------------------------------------------------------------
# 429 retry behaviour
# ---------------------------------------------------------------------------


def test_429_triggers_single_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pre-v0.4.12 a 429 raised straight to the caller. Now: sleep,
    retry once, succeed. Sleep is monkey-patched to zero so the test
    runs instantly."""
    from app.etag_store import InMemoryETagStore, set_active_store

    set_active_store(InMemoryETagStore())

    sleeps_observed: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps_observed.append(seconds)

    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    responses = [
        httpx.Response(429, headers={"Retry-After": "2"}),
        httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            json={"resultados": []},
        ),
    ]
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return responses[call_count["n"] - 1]

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)

    async def go():
        try:
            return await cima_client._request("GET", "medicamentos", client=client)
        finally:
            await client.aclose()

    result = _run(go())

    assert call_count["n"] == 2, "429 must trigger exactly one retry"
    assert result == {"resultados": []}
    # We slept once. Retry-After=2 + a jitter of 0-0.5, so 2.0..2.5.
    assert len(sleeps_observed) == 1
    assert 2.0 <= sleeps_observed[0] <= 2.5


def test_429_default_delay_when_header_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.etag_store import InMemoryETagStore, set_active_store

    set_active_store(InMemoryETagStore())

    sleeps_observed: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps_observed.append(seconds)

    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    responses = [
        httpx.Response(429),
        httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            json={"resultados": []},
        ),
    ]
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return responses[call_count["n"] - 1]

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)

    async def go():
        try:
            return await cima_client._request("GET", "medicamentos", client=client)
        finally:
            await client.aclose()

    _run(go())

    # Default 1.0s + jitter 0-0.5 → 1.0..1.5.
    assert len(sleeps_observed) == 1
    assert 1.0 <= sleeps_observed[0] <= 1.5


def test_persistent_429_after_retry_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    """If retry also returns 429, the second 429 surfaces as
    ``HTTPStatusError`` to the caller — we don't loop."""
    from app.etag_store import InMemoryETagStore, set_active_store

    set_active_store(InMemoryETagStore())

    async def fake_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)

    async def go():
        try:
            await cima_client._request("GET", "medicamentos", client=client)
        finally:
            await client.aclose()

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        _run(go())
    assert exc_info.value.response.status_code == 429
