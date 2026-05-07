# app/logging_setup.py
"""Logging configuration — plain structured stdlib logging.

Console + rotating file handler with gzip compression. No OTel coupling
by default; downstream consumers can replace the formatter via a startup
hook to add trace/correlation IDs.

Also exposes ``apply_mcp_log_level`` — the bridge from the MCP
``logging/setLevel`` request (RFC 5424 string levels per spec) to the
stdlib logger hierarchy. Wired into FastMCP from ``app.stdio_server``.
"""

from __future__ import annotations

import gzip
import logging
import os
import shutil
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from app.config import settings

_LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


class _RenameUvicornErrorFilter(logging.Filter):
    """Rewrite the misleading ``uvicorn.error`` logger name to plain
    ``uvicorn`` in emitted records.

    Why this exists: uvicorn's main lifecycle logger is named
    ``uvicorn.error`` for historical reasons (the project split access
    vs everything-else logs, and the everything-else channel kept the
    legacy name). It emits *all* severity levels through that name —
    including the INFO-level "Started server process", "Waiting for
    application startup", "Uvicorn running on ..." lines you see at
    boot. Users reasonably read "uvicorn.error" as "this is an error",
    when in fact only the level field carries severity. Renaming the
    record keeps stdlib logger hierarchy intact for filters that care
    while making the human-readable output unambiguous.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        if record.name == "uvicorn.error":
            record.name = "uvicorn"
        return True


# Spec ref: MCP logging utility (modelcontextprotocol.io/specification/server/utilities/logging)
# uses RFC 5424 syslog levels. Map them down to the stdlib's narrower set.
_MCP_LEVEL_TO_STDLIB: dict[str, int] = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "notice": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
    "alert": logging.CRITICAL,
    "emergency": logging.CRITICAL,
}


def apply_mcp_log_level(level: str) -> int:
    """Apply an MCP ``logging/setLevel`` request to the stdlib logger tree.

    Updates the root logger plus the project's ``mcp.aemps`` logger so
    handlers actually emit the new level. Returns the resolved stdlib level
    so callers can log a confirmation if useful.

    Unknown levels fall back to ``INFO`` rather than raising — this is a
    runtime client request, not a config error.
    """
    py_level = _MCP_LEVEL_TO_STDLIB.get(level.lower(), logging.INFO)
    logging.getLogger().setLevel(py_level)
    logging.getLogger("mcp.aemps").setLevel(py_level)
    return py_level


def _namer(name: str) -> str:
    return f"{name}.gz"


def _rotator(source: str, dest: str) -> None:
    with open(source, "rb") as sf, gzip.open(dest, "wb") as df:
        shutil.copyfileobj(sf, df)
    os.remove(source)


def configure_logging() -> logging.Logger:
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    root.setLevel(log_level)

    fmt = logging.Formatter(_LOG_FORMAT)

    rename_filter = _RenameUvicornErrorFilter()

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    console.addFilter(rename_filter)
    root.addHandler(console)

    for name in ("uvicorn", "uvicorn.error"):
        uv = logging.getLogger(name)
        uv.handlers = []
        uv.propagate = True
    uv_access = logging.getLogger("uvicorn.access")
    uv_access.handlers = []
    uv_access.propagate = False

    # File handler is best-effort. ``settings.log_dir`` is empty when no
    # writable path was found (sandboxed Claude Desktop launches, Docker
    # without a log mount, etc.) — in that case we run with console-only
    # logging instead of crashing the process.
    if settings.log_dir:
        try:
            log_dir = Path(settings.log_dir)
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / "mcp_aemps.log"
            file_handler = TimedRotatingFileHandler(
                filename=str(log_file),
                when="midnight",
                interval=1,
                backupCount=settings.log_retention_days,
                encoding="utf-8",
                utc=True,
            )
            file_handler.namer = _namer
            file_handler.rotator = _rotator
            file_handler.setFormatter(fmt)
            file_handler.addFilter(rename_filter)
            root.addHandler(file_handler)
        except Exception as exc:  # noqa: BLE001
            # Mirror the file-handler failure to stderr so a deployer
            # debugging "where are my logs?" finds the trail.
            root.warning(
                "File logging disabled: could not open %s (%s)",
                settings.log_dir,
                type(exc).__name__,
            )

    logger = logging.getLogger("mcp.aemps")
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("Config (safe): %s", settings.safe_dump())

    return logger
