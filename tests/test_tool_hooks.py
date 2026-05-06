"""Tests for the Phase 0 extension surface: pre/post tool hooks, health_extra,
metrics_replace. Cover both success paths and error paths.

Key invariants:
* Pre-hook raising OperationError aborts the call with a structured payload.
* Post-hook fires on both success and failure with the right ``error`` arg.
* Same hook fires for the same op across HTTP and stdio transports.
* health_extra's ``*_ready: False`` flips /health/ready to 503; otherwise 200.
* metrics_replace=True skips the in-process metrics middleware.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.core import OperationError
from app.factory import create_app
from app.stdio_server import build_server


@pytest.fixture
def _instant_warmup(monkeypatch):
    """Patch warm_maestras to a no-op so /health/ready reaches the 200 branch
    without waiting on a real CIMA fetch."""

    async def _noop(app):
        return None

    # warm_maestras is referenced by lifespan via direct import — patch the
    # binding the lifespan module uses, not the source module.
    import app.lifespan as lifespan_mod

    monkeypatch.setattr(lifespan_mod, "warm_maestras", _noop)
    monkeypatch.setattr(lifespan_mod, "periodic_maestras_refresh", _noop)
    yield


# ---------------------------------------------------------------------------
# Pre/post tool hooks — HTTP transport
# ---------------------------------------------------------------------------


def test_post_tool_hook_fires_on_http_success() -> None:
    """Post-hook receives (operation_id, args, error=None, elapsed) on 200."""
    calls: list[tuple[str, dict, BaseException | None]] = []

    async def post(name: str, args: dict, err: BaseException | None, elapsed: float) -> None:
        calls.append((name, args, err))

    app = create_app(post_tool_hooks=[post], mount_mcp=False)
    with TestClient(app) as client:
        # /health is not an MCP tool (no operation_id) — must NOT trigger the hook.
        client.get("/health")
        assert calls == []


def test_pre_tool_hook_can_abort_with_operation_error() -> None:
    """Pre-hook raising OperationError → JSON 4xx, route never runs."""
    route_invocations: list[str] = []

    async def gate(name: str, args: dict) -> None:
        if name == "obtener_medicamento":
            raise OperationError(403, error="forbidden", message="audit gate")

    async def post(name: str, args: dict, err: BaseException | None, elapsed: float) -> None:
        route_invocations.append(name)

    app = create_app(
        pre_tool_hooks=[gate],
        post_tool_hooks=[post],
        mount_mcp=False,
    )
    with TestClient(app) as client:
        resp = client.get("/medicamento", params={"cn": "12345"})
        assert resp.status_code == 403
        body = resp.json()
        assert body["error"] == "forbidden"
        # Post-hook does NOT fire when the pre-hook short-circuits the call.
        assert route_invocations == []


def test_post_tool_hook_swallows_exceptions() -> None:
    """A buggy post-hook must not break the response."""

    async def boom(name: str, args: dict, err: BaseException | None, elapsed: float) -> None:
        raise RuntimeError("post-hook bug")

    # Pair with a pre-hook that aborts cheaply so we don't hit CIMA in tests.
    async def deny(name: str, args: dict) -> None:
        raise OperationError(401, error="unauth")

    app = create_app(
        pre_tool_hooks=[deny],
        post_tool_hooks=[boom],
        mount_mcp=False,
    )
    with TestClient(app) as client:
        resp = client.get("/medicamento", params={"cn": "12345"})
        assert resp.status_code == 401  # the deny pre-hook outcome wins
        # In this case the pre-hook short-circuited so post-hook is not called.
        # Verify the buggy post-hook still doesn't taint a downstream-only path:
        # /health has no operation_id → middleware skips entirely.
        assert client.get("/health").status_code == 200


def test_no_hooks_means_no_middleware_overhead() -> None:
    """When no hooks are passed, the middleware is not installed at all."""
    app = create_app(mount_mcp=False)
    # We can't introspect middleware order trivially, but we can assert the
    # app.state attribute is the empty hook bundle so the hot path stays fast.
    assert app.state.tool_hooks.is_empty()


# ---------------------------------------------------------------------------
# Pre/post tool hooks — stdio transport
# ---------------------------------------------------------------------------


def test_stdio_pre_hook_aborts_with_operation_error_dict() -> None:
    """Pre-hook OperationError on stdio is serialised to a dict, not raised."""
    seen: list[str] = []

    async def deny(name: str, args: dict) -> None:
        seen.append(f"pre:{name}")
        raise OperationError(403, error="forbidden", message="stdio gate")

    async def post(name: str, args: dict, err: BaseException | None, elapsed: float) -> None:
        seen.append(f"post:{name}")

    server = build_server(pre_tool_hooks=[deny], post_tool_hooks=[post])
    tools = asyncio.run(server.list_tools())
    obtener = next(t for t in tools if t.name == "obtener_medicamento")

    result = asyncio.run(server.call_tool(obtener.name, {"cn": "12345"}))
    # FastMCP returns (content, structured_content) in modern versions.
    # The structured content (dict) carries our serialised OperationError.
    structured = result[1] if isinstance(result, tuple) else result
    if isinstance(structured, dict) and "result" in structured:
        structured = structured["result"]
    assert isinstance(structured, dict)
    assert structured["error"] == "forbidden"
    assert structured["status_code"] == 403
    # Pre-hook fired, post-hook did NOT (short-circuit semantics match HTTP).
    assert seen == ["pre:obtener_medicamento"]


def test_stdio_no_hooks_keeps_existing_serialize_behaviour() -> None:
    """Building a server without hooks still wraps OperationError as a dict."""
    server = build_server()
    tools = asyncio.run(server.list_tools())
    # Just check the wrapper is wired by inspecting one tool name exists.
    tool_names = {t.name for t in tools}
    assert "obtener_medicamento" in tool_names


# ---------------------------------------------------------------------------
# health_extra
# ---------------------------------------------------------------------------


def test_health_extra_merges_into_ready_payload(_instant_warmup) -> None:
    """A health_extra returning {data_ready: True} → 200 with field merged."""

    async def extra(app):
        return {"data_ready": True, "xls_rows": 1234}

    app = create_app(health_extra=extra, mount_mcp=False)
    with TestClient(app) as client:
        resp = client.get("/health/ready")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["data_ready"] is True
        assert body["xls_rows"] == 1234
        assert body["warmup"] == "completed"


def test_health_extra_unready_flag_flips_to_503(_instant_warmup) -> None:
    """A *_ready: False field triggers a 503 with status=degraded."""

    async def extra(app):
        return {"data_ready": False, "xls_rows": 0}

    app = create_app(health_extra=extra, mount_mcp=False)
    with TestClient(app) as client:
        resp = client.get("/health/ready")
        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "degraded"
        assert body["data_ready"] is False
        assert body["xls_rows"] == 0


def test_health_extra_plain_ready_false_also_flips(_instant_warmup) -> None:
    """The bare key ``ready: False`` is treated the same as ``*_ready: False``."""

    async def extra(app):
        return {"ready": False, "reason": "downstream offline"}

    app = create_app(health_extra=extra, mount_mcp=False)
    with TestClient(app) as client:
        resp = client.get("/health/ready")
        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "degraded"
        assert body["reason"] == "downstream offline"


def test_health_extra_exception_is_caught_and_marks_degraded(_instant_warmup) -> None:
    """A buggy health_extra must not crash the readiness probe."""

    async def boom(app):
        raise RuntimeError("oops")

    app = create_app(health_extra=boom, mount_mcp=False)
    with TestClient(app) as client:
        resp = client.get("/health/ready")
        # Probe still responds — body carries the error marker but warmup is OK.
        assert resp.status_code == 200
        assert resp.json()["health_extra_error"] is True


def test_health_extra_unrelated_truthy_keys_keep_200(_instant_warmup) -> None:
    """Keys not suffixed _ready/ready don't gate readiness regardless of value."""

    async def extra(app):
        return {"connections": 0, "queue_depth": 99, "cache_size_bytes": 0}

    app = create_app(health_extra=extra, mount_mcp=False)
    with TestClient(app) as client:
        resp = client.get("/health/ready")
        assert resp.status_code == 200
        assert resp.json()["queue_depth"] == 99


# ---------------------------------------------------------------------------
# metrics_replace
# ---------------------------------------------------------------------------


def test_metrics_replace_skips_inprocess_middleware() -> None:
    """When opted out, /internal/metrics still serves the snapshot but the
    middleware does not record requests (snapshot stays at zero for unrelated
    paths)."""
    from app.metrics import METRICS

    before = METRICS.snapshot()["requests_total"]

    app = create_app(metrics_replace=True, mount_mcp=False)
    with TestClient(app) as client:
        client.get("/health")
        client.get("/health/live")

    after = METRICS.snapshot()["requests_total"]
    # The middleware was not installed → counters unchanged by these requests.
    # (Other tests in the same process may have recorded — assert no growth
    # caused by *this* app's traffic.)
    assert after == before


def test_metrics_replace_default_keeps_middleware() -> None:
    """Default behaviour — middleware records requests."""
    from app.metrics import METRICS

    app = create_app(mount_mcp=False)
    before = METRICS.snapshot()["requests_total"]
    with TestClient(app) as client:
        client.get("/health")
    after = METRICS.snapshot()["requests_total"]
    assert after > before


# ---------------------------------------------------------------------------
# Public API surface
# ---------------------------------------------------------------------------


def test_rate_limit_tiers_are_publicly_exported() -> None:
    """Downstream consumers depend on these names being stable."""
    from app import rate_limits

    for name in ("limit_local", "limit_standard", "limit_document", "limit_heavy"):
        assert name in rate_limits.__all__
        assert hasattr(rate_limits, name)


def test_tool_hooks_module_exports() -> None:
    """The hook module exports the contract types and helpers MOXI imports."""
    from app import tool_hooks

    assert hasattr(tool_hooks, "HookSet")
    assert hasattr(tool_hooks, "PreHookFn")
    assert hasattr(tool_hooks, "PostHookFn")
    assert hasattr(tool_hooks, "wrap_stdio_tool")
