# app/logging_setup.py
"""Logging configuration — plain structured stdlib logging.

Community Edition: console + rotating file handler with gzip compression.
No OTel coupling. Enterprise editions add OTel correlation by replacing
the formatter through a startup hook.
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


def _namer(name: str) -> str:
    return f"{name}.gz"


def _rotator(source: str, dest: str) -> None:
    with open(source, "rb") as sf, gzip.open(dest, "wb") as df:
        shutil.copyfileobj(sf, df)
    os.remove(source)


def configure_logging() -> logging.Logger:
    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "mcp_aemps.log"

    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    root.setLevel(log_level)

    fmt = logging.Formatter(_LOG_FORMAT)

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    for name in ("uvicorn", "uvicorn.error"):
        uv = logging.getLogger(name)
        uv.handlers = []
        uv.propagate = True
    uv_access = logging.getLogger("uvicorn.access")
    uv_access.handlers = []
    uv_access.propagate = False

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
    root.addHandler(file_handler)

    logger = logging.getLogger("mcp.aemps")
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("Config (safe): %s", settings.safe_dump())

    return logger
