# app/metrics.py
"""Lightweight in-process metrics — zero external dependencies.

Returns a JSON snapshot of in-process counters and basic system info.
For Prometheus-style metrics + OTel export, use the Enterprise edition.

This is enough for:
- Verifying the server is alive and serving traffic
- Spot-checking request volume / error rate
- Debugging cache backend mode and uptime
"""

from __future__ import annotations

import threading
import time
from collections import Counter
from typing import Any

from app.config import settings


class _Snapshot:
    """Thread-safe in-process counters."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._started_at = time.time()
        self._requests = Counter()
        self._statuses = Counter()
        self._errors = 0

    def record(self, *, path: str, status: int) -> None:
        with self._lock:
            self._requests[path] += 1
            self._statuses[status] += 1
            if status >= 500:
                self._errors += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "version": settings.mcp_aemps_version,
                "uptime_seconds": round(time.time() - self._started_at, 1),
                "started_at": self._started_at,
                "requests_total": sum(self._requests.values()),
                "requests_by_path": dict(self._requests.most_common(20)),
                "status_codes": dict(self._statuses),
                "errors_5xx": self._errors,
            }


METRICS = _Snapshot()


async def metrics_middleware(request, call_next):
    """ASGI middleware — record (path, status) for every request."""
    response = await call_next(request)
    try:
        path = request.url.path
        # Avoid blowing up the cardinality with /docs assets, etc.
        if not path.startswith(("/static", "/openapi.json")):
            METRICS.record(path=path, status=response.status_code)
    except Exception:
        pass
    return response
