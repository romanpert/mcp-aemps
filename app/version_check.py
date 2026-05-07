# app/version_check.py
"""Outdated-version warning emitted at server startup.

Pings PyPI's JSON metadata for ``mcp-aemps`` and compares the latest
published version to the running one. If the running version is older
the user gets a single WARNING line with the upgrade command — once
per process startup, never on a hot path.

Design constraints:

- **Best-effort.** Network failures, JSON parse errors, missing fields:
  log at DEBUG and return. Never crash startup, never spam the user.
- **Bounded.** 3-second total timeout (handshake + response). PyPI is
  fast and CDN-cached; if it's slow there's no benefit to waiting.
- **Opt-out.** ``MCP_AEMPS_SKIP_UPDATE_CHECK=1`` skips the check
  entirely. Useful for offline / air-gapped deployments and for tests.
- **Single source.** Only PyPI is queried. The npm wrapper version is
  packaging-only metadata (npm wrapper auto-pulls latest PyPI), so a
  separate npm check would be misleading.

The check is fire-and-forget — invoked from ``app.lifespan`` (HTTP) and
``app.stdio_server.main`` (stdio). Either path runs it as an async
task so the server starts immediately even if PyPI is slow.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re

import httpx

logger = logging.getLogger("mcp.aemps.version_check")

PYPI_JSON_URL = "https://pypi.org/pypi/mcp-aemps/json"
TIMEOUT_SECONDS = 3.0
SKIP_ENV_VAR = "MCP_AEMPS_SKIP_UPDATE_CHECK"

# Strict semver-ish parser. PyPI versions for this project are always
# X.Y.Z; anything fancier (alpha, rc, +local) is parsed leniently and
# the comparison falls back to string equality (no false-positive
# "outdated").
_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)")


def _parse_version(v: str) -> tuple[int, int, int] | None:
    m = _SEMVER_RE.match(v.strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


async def fetch_latest_pypi_version() -> str | None:
    """Hit PyPI's JSON endpoint, return the ``info.version`` string or
    ``None`` on any failure. Public so tests can monkey-patch it."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            resp = await client.get(PYPI_JSON_URL)
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        logger.debug("version check skipped: PyPI fetch failed (%s)", type(exc).__name__)
        return None
    return (data.get("info") or {}).get("version")


async def check_outdated(running_version: str) -> None:
    """Compare ``running_version`` to PyPI latest. Emit a single WARNING
    if the running version is behind. Always returns None — fire-and-
    forget contract.

    Skipped when ``MCP_AEMPS_SKIP_UPDATE_CHECK=1`` is set.
    """
    if os.environ.get(SKIP_ENV_VAR, "").strip() in {"1", "true", "TRUE", "yes"}:
        return

    latest = await fetch_latest_pypi_version()
    if not latest:
        return

    running_parsed = _parse_version(running_version)
    latest_parsed = _parse_version(latest)
    # Ambiguous: pre-release / source build / unparseable. Don't warn
    # because we can't reliably compare.
    if running_parsed is None or latest_parsed is None:
        logger.debug(
            "version check inconclusive: running=%s latest=%s (unparseable)",
            running_version,
            latest,
        )
        return

    if running_parsed >= latest_parsed:
        logger.debug("version check: running=%s latest=%s (up-to-date)", running_version, latest)
        return

    logger.warning(
        "mcp-aemps %s is outdated — latest on PyPI is %s. "
        "Upgrade: `pip install --upgrade mcp-aemps` "
        "(or `uvx mcp-aemps@latest stdio` if running via uvx). "
        "Set %s=1 to silence this check.",
        running_version,
        latest,
        SKIP_ENV_VAR,
    )


def schedule_check(running_version: str) -> asyncio.Task[None] | None:
    """Schedule the check as a background task in the current loop.
    Returns the task so callers can optionally await it (HTTP lifespan
    won't; stdio main can if it wants ordering).

    Returns ``None`` if no event loop is currently running (defensive
    — both call sites do have one)."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return None
    return loop.create_task(check_outdated(running_version))


__all__ = [
    "PYPI_JSON_URL",
    "SKIP_ENV_VAR",
    "TIMEOUT_SECONDS",
    "check_outdated",
    "fetch_latest_pypi_version",
    "schedule_check",
]
