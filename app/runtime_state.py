# app/runtime_state.py
"""Runtime state — port discovery, PID file, free-port scanning.

The server writes its actually-bound port to `state_dir() / "runtime.json"`
so that `mcp-aemps install` can pick it up automatically. This decouples
the install step from the up step: the user can change the port without
re-running the installer.

Default port: 8765 — chosen to avoid collisions with the very common 8000
(Django/uvicorn dev), 5000 (Flask), 3000 (Node/Next), 4000 (Phoenix), and
similar widely-used ports. 8765 is also memorable (sequential digits).
"""

from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 8765
PATH = "/mcp"

_RUNTIME_FILE = "runtime.json"


def state_dir() -> Path:
    """Per-user state directory for runtime artifacts."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "mcp-aemps"
    if sys.platform.startswith("win"):
        local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(local) / "mcp-aemps"
    xdg = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(xdg) / "mcp-aemps"


def runtime_file() -> Path:
    return state_dir() / _RUNTIME_FILE


def write_runtime(*, host: str, port: int, pid: int | None = None) -> None:
    """Persist the actually-bound host/port (and optional PID)."""
    d = state_dir()
    d.mkdir(parents=True, exist_ok=True)
    payload = {"host": host, "port": port}
    if pid is not None:
        payload["pid"] = pid
    runtime_file().write_text(json.dumps(payload, indent=2), encoding="utf-8")
    try:
        os.chmod(runtime_file(), 0o600)
    except OSError:
        pass


def read_runtime() -> dict | None:
    """Return persisted {host, port, pid?} or None if not available."""
    f = runtime_file()
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def clear_runtime() -> None:
    f = runtime_file()
    try:
        f.unlink()
    except FileNotFoundError:
        pass


def find_free_port(start: int = DEFAULT_PORT, host: str = "0.0.0.0", limit: int = 50) -> int:
    """Return the first free TCP port >= start (within `limit` attempts)."""
    port = start
    for _ in range(limit):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
                return port
            except OSError:
                port += 1
    raise OSError(f"No free port found in range {start}..{start + limit}")


def resolve_default_url() -> str:
    """Build the install-time URL based on the last-bound port (or default)."""
    rt = read_runtime()
    if rt and "port" in rt:
        host = rt.get("host", DEFAULT_HOST)
        # Always advertise localhost to clients — even if the server bound 0.0.0.0
        # the client connects from the same machine over loopback.
        if host in ("0.0.0.0", "::", "::0"):
            host = DEFAULT_HOST
        return f"http://{host}:{rt['port']}{PATH}"
    return f"http://{DEFAULT_HOST}:{DEFAULT_PORT}{PATH}"
