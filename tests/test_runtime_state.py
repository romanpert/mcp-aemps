"""Tests for runtime port discovery and metrics."""

from __future__ import annotations

from unittest.mock import patch


def test_resolve_default_url_falls_back_to_static_default() -> None:
    """When no runtime file exists, install URL falls back to the documented default."""
    from app.runtime_state import DEFAULT_HOST, DEFAULT_PORT, PATH, resolve_default_url

    with patch("app.runtime_state.read_runtime", return_value=None):
        url = resolve_default_url()
    assert url == f"http://{DEFAULT_HOST}:{DEFAULT_PORT}{PATH}"


def test_resolve_default_url_uses_runtime_port_when_present() -> None:
    """When the server has run, install URL must match the bound port."""
    from app.runtime_state import resolve_default_url

    with patch("app.runtime_state.read_runtime", return_value={"host": "localhost", "port": 9999}):
        url = resolve_default_url()
    assert url == "http://localhost:9999/mcp"


def test_resolve_default_url_advertises_localhost_for_wildcard_bind() -> None:
    """If the server bound 0.0.0.0, clients still connect to localhost."""
    from app.runtime_state import resolve_default_url

    with patch("app.runtime_state.read_runtime", return_value={"host": "0.0.0.0", "port": 8765}):
        url = resolve_default_url()
    assert "localhost" in url


def test_find_free_port_returns_starting_port_when_free() -> None:
    """In normal conditions, find_free_port should return the requested port."""
    from app.runtime_state import find_free_port

    # Pick a high port unlikely to be in use during tests.
    port = find_free_port(start=37121, host="127.0.0.1")
    assert port == 37121


def test_metrics_records_request() -> None:
    from app.metrics import _Snapshot

    s = _Snapshot()
    s.record(path="/medicamento", status=200)
    s.record(path="/medicamento", status=200)
    s.record(path="/health", status=200)
    s.record(path="/medicamento", status=500)

    snap = s.snapshot()
    assert snap["requests_total"] == 4
    assert snap["requests_by_path"]["/medicamento"] == 3
    assert snap["status_codes"][200] == 3
    assert snap["status_codes"][500] == 1
    assert snap["errors_5xx"] == 1
    assert "version" in snap
    assert "uptime_seconds" in snap
