"""Outdated-version warning contract tests.

Network access is mocked via ``unittest.mock`` — the test never hits
PyPI.
"""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, patch

import pytest

from app.version_check import (
    SKIP_ENV_VAR,
    _parse_version,
    check_outdated,
)


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# _parse_version invariants
# ---------------------------------------------------------------------------


def test_parse_version_handles_xyz() -> None:
    assert _parse_version("0.4.10") == (0, 4, 10)
    assert _parse_version("1.0.0") == (1, 0, 0)
    assert _parse_version("12.34.567") == (12, 34, 567)


def test_parse_version_returns_none_for_pep440_extras() -> None:
    """Pre-releases / source builds are intentionally rejected — we only
    want unambiguous comparisons. ``None`` triggers the "inconclusive"
    branch in check_outdated which skips the warning."""
    # Source-build sentinel from app.config._resolve_version
    assert _parse_version("0.0.0+source") == (0, 0, 0)  # base parses
    # But anything not starting with X.Y.Z fails
    assert _parse_version("v0.4.10") is None
    assert _parse_version("not-a-version") is None
    assert _parse_version("") is None


# ---------------------------------------------------------------------------
# check_outdated behaviour
# ---------------------------------------------------------------------------


def test_no_warning_when_running_matches_latest(caplog: pytest.LogCaptureFixture) -> None:
    """Running the latest published version: silent (DEBUG only, no
    user-facing WARNING)."""
    with patch(
        "app.version_check.fetch_latest_pypi_version",
        AsyncMock(return_value="0.4.11"),
    ):
        with caplog.at_level(logging.WARNING, logger="mcp.aemps.version_check"):
            _run(check_outdated("0.4.11"))
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_no_warning_when_running_ahead_of_latest(caplog: pytest.LogCaptureFixture) -> None:
    """Local dev builds ahead of PyPI shouldn't produce a downgrade
    warning."""
    with patch(
        "app.version_check.fetch_latest_pypi_version",
        AsyncMock(return_value="0.4.10"),
    ):
        with caplog.at_level(logging.WARNING, logger="mcp.aemps.version_check"):
            _run(check_outdated("0.4.11"))
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_warning_emitted_when_running_behind(caplog: pytest.LogCaptureFixture) -> None:
    """Running an older version must produce a single actionable
    WARNING. The test pins the upgrade-command substring so a
    refactor that removes the suggestion fails CI."""
    with patch(
        "app.version_check.fetch_latest_pypi_version",
        AsyncMock(return_value="0.4.11"),
    ):
        with caplog.at_level(logging.WARNING, logger="mcp.aemps.version_check"):
            _run(check_outdated("0.4.5"))
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1, [r.message for r in caplog.records]
    msg = warnings[0].getMessage()
    assert "0.4.5" in msg and "0.4.11" in msg
    assert "pip install --upgrade mcp-aemps" in msg
    assert SKIP_ENV_VAR in msg  # opt-out instruction surfaced


def test_skip_env_var_silences_warning(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(SKIP_ENV_VAR, "1")
    fetch_mock = AsyncMock(return_value="0.4.11")
    with patch("app.version_check.fetch_latest_pypi_version", fetch_mock):
        with caplog.at_level(logging.WARNING, logger="mcp.aemps.version_check"):
            _run(check_outdated("0.4.5"))
    assert fetch_mock.await_count == 0, "skip env var should short-circuit before fetch"
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_silent_on_pypi_unreachable(caplog: pytest.LogCaptureFixture) -> None:
    """Network failure ⇒ no WARNING (we don't know if we're outdated)."""
    with patch(
        "app.version_check.fetch_latest_pypi_version",
        AsyncMock(return_value=None),
    ):
        with caplog.at_level(logging.WARNING, logger="mcp.aemps.version_check"):
            _run(check_outdated("0.4.5"))
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_silent_on_unparseable_running_version(caplog: pytest.LogCaptureFixture) -> None:
    """Source builds (``0.0.0+source`` from app.config._resolve_version)
    parse the (0,0,0) base and would otherwise look outdated. Other
    unparseable strings (``v1.0``) skip without warning."""
    with patch(
        "app.version_check.fetch_latest_pypi_version",
        AsyncMock(return_value="0.4.11"),
    ):
        with caplog.at_level(logging.WARNING, logger="mcp.aemps.version_check"):
            _run(check_outdated("v1.0"))
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


# ---------------------------------------------------------------------------
# cima_client shared client invariant — pinned because it's the v0.4.11
# perf fix that costs a lot to regress (every CIMA call paying TLS again)
# ---------------------------------------------------------------------------


def test_shared_cima_client_is_singleton_per_process() -> None:
    """``_get_shared_client`` must hand out the same instance on every
    call within the same loop. A regression here would silently revert
    the v0.4.11 connection-pool fix."""
    from app.cima_client import _get_shared_client, aclose_shared_client

    async def go():
        a = await _get_shared_client()
        b = await _get_shared_client()
        try:
            assert a is b
        finally:
            await aclose_shared_client()

    _run(go())
