# app/installers.py
"""One-command installers for popular MCP-compatible clients.

Each installer is idempotent (running twice is a no-op), atomic (either the
write succeeds fully or not at all), and additive (preserves existing entries
in the user's config).

Supported clients:
- Claude Desktop  (via mcp-remote bridge — the only format Claude Desktop's
                   config file currently validates for HTTP MCP servers)
- Claude Code     (`claude mcp add` CLI preferred, fallback to ~/.claude.json)
- Codex CLI       (~/.codex/config.toml)
- VS Code         (settings.json mcp.servers OR per-workspace .vscode/mcp.json)
- Cursor          (~/.cursor/mcp.json)
- Windsurf        (~/.codeium/windsurf/mcp_config.json)
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from app.runtime_state import resolve_default_url

SERVER_KEY = "mcp-aemps"


def _default_url() -> str:
    """Resolve the URL to use when none is provided.

    Reads the server's runtime port file (written by `mcp-aemps up/dev`) so
    installers always pick up the *actual* port the server is listening on.
    Falls back to the static default if no server has run yet.
    """
    return resolve_default_url()


# ---------------------------------------------------------------------------
# Common
# ---------------------------------------------------------------------------
@dataclass
class InstallResult:
    client: str
    config_path: Path
    action: str  # "added" | "updated" | "unchanged" | "removed"
    message: str


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _set_nested(d: dict, keys: list[str], value: dict) -> dict:
    """Set d[k1][k2]...[kN] = value, creating intermediate dicts as needed."""
    cur = d
    for k in keys[:-1]:
        cur = cur.setdefault(k, {})
    cur[keys[-1]] = value
    return d


def _get_nested(d: dict, keys: list[str]) -> dict | None:
    cur: object = d
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
        if cur is None:
            return None
    return cur if isinstance(cur, dict) else None


def _delete_nested(d: dict, keys: list[str]) -> bool:
    """Delete d[k1]...[kN]. Return True if removed."""
    cur: object = d
    for k in keys[:-1]:
        if not isinstance(cur, dict):
            return False
        cur = cur.get(k)
    if isinstance(cur, dict) and keys[-1] in cur:
        del cur[keys[-1]]
        return True
    return False


# ---------------------------------------------------------------------------
# Claude Desktop
# ---------------------------------------------------------------------------
def claude_desktop_config_path() -> Path:
    """Resolve the Claude Desktop config path per OS."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    if sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(appdata) / "Claude" / "claude_desktop_config.json"
    xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(xdg) / "Claude" / "claude_desktop_config.json"


def install_claude_desktop(
    *,
    url: str | None = None,
    server_key: str = SERVER_KEY,
    config_path: Path | None = None,
) -> InstallResult:
    """Add or update the mcp-aemps entry in claude_desktop_config.json.

    Claude Desktop's config file currently only validates **stdio** server
    entries (remote/HTTP MCP servers go through the "Connectors" UI, not
    this file). To expose an HTTP MCP server we bridge stdio↔HTTP with the
    official `mcp-remote` npm package, executed via `npx`.
    """
    url = url or _default_url()
    path = config_path or claude_desktop_config_path()
    config = _read_json(path)
    config.setdefault("mcpServers", {})

    desired = {"command": "npx", "args": ["-y", "mcp-remote", url]}
    existing = config["mcpServers"].get(server_key)

    if existing == desired:
        return InstallResult("Claude Desktop", path, "unchanged", f"{server_key} already configured")

    action = "updated" if existing else "added"
    config["mcpServers"][server_key] = desired
    _atomic_write_json(path, config)
    return InstallResult(
        "Claude Desktop",
        path,
        action,
        f"{server_key} -> {url} (mcp-remote bridge); restart Claude Desktop",
    )


def uninstall_claude_desktop(
    *, server_key: str = SERVER_KEY, config_path: Path | None = None
) -> InstallResult:
    path = config_path or claude_desktop_config_path()
    config = _read_json(path)
    servers = config.get("mcpServers", {})
    if server_key in servers:
        del servers[server_key]
        _atomic_write_json(path, config)
        return InstallResult("Claude Desktop", path, "removed", f"{server_key} removed")
    return InstallResult("Claude Desktop", path, "unchanged", f"{server_key} was not present")


# ---------------------------------------------------------------------------
# Claude Code
# ---------------------------------------------------------------------------
def claude_code_config_path() -> Path:
    return Path.home() / ".claude.json"


def _claude_cli_available() -> bool:
    return shutil.which("claude") is not None


def install_claude_code(
    *,
    url: str | None = None,
    server_key: str = SERVER_KEY,
    scope: str = "user",
    config_path: Path | None = None,
    use_cli: bool | None = None,
) -> InstallResult:
    """Register mcp-aemps with Claude Code. CLI-preferred, JSON fallback."""
    url = url or _default_url()
    cli_allowed = config_path is None and (use_cli is None or use_cli)
    if cli_allowed and _claude_cli_available():
        try:
            cmd = ["claude", "mcp", "add", "--scope", scope, "--transport", "http", server_key, url]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                return InstallResult(
                    "Claude Code",
                    Path("(via `claude mcp add`)"),
                    "added",
                    f"{server_key} -> {url} (scope={scope})",
                )
            stderr = (result.stderr or "").lower()
            if "already exists" in stderr or "already configured" in stderr:
                return InstallResult(
                    "Claude Code",
                    Path("(via `claude mcp add`)"),
                    "unchanged",
                    f"{server_key} already configured",
                )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    path = config_path or claude_code_config_path()
    config = _read_json(path)
    config.setdefault("mcpServers", {})
    desired = {"type": "http", "url": url}
    existing = config["mcpServers"].get(server_key)

    if existing == desired:
        return InstallResult("Claude Code", path, "unchanged", f"{server_key} already configured")

    action = "updated" if existing else "added"
    config["mcpServers"][server_key] = desired
    _atomic_write_json(path, config)
    return InstallResult("Claude Code", path, action, f"{server_key} -> {url}")


def uninstall_claude_code(
    *,
    server_key: str = SERVER_KEY,
    config_path: Path | None = None,
    use_cli: bool | None = None,
) -> InstallResult:
    cli_allowed = config_path is None and (use_cli is None or use_cli)
    if cli_allowed and _claude_cli_available():
        try:
            result = subprocess.run(
                ["claude", "mcp", "remove", server_key],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                return InstallResult(
                    "Claude Code", Path("(via `claude mcp remove`)"), "removed", f"{server_key} removed"
                )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    path = config_path or claude_code_config_path()
    config = _read_json(path)
    servers = config.get("mcpServers", {})
    if server_key in servers:
        del servers[server_key]
        _atomic_write_json(path, config)
        return InstallResult("Claude Code", path, "removed", f"{server_key} removed")
    return InstallResult("Claude Code", path, "unchanged", f"{server_key} was not present")


# ---------------------------------------------------------------------------
# Codex CLI
# ---------------------------------------------------------------------------
def codex_config_path() -> Path:
    return Path.home() / ".codex" / "config.toml"


def install_codex(
    *,
    url: str | None = None,
    server_key: str = SERVER_KEY,
    config_path: Path | None = None,
) -> InstallResult:
    """Append a [mcp_servers.<name>] block to ~/.codex/config.toml (idempotent)."""
    url = url or _default_url()
    path = config_path or codex_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_text = path.read_text(encoding="utf-8") if path.exists() else ""

    block = f'\n[mcp_servers.{server_key}]\nurl = "{url}"\ntransport = "http"\n'
    header = f"[mcp_servers.{server_key}]"

    if header in existing_text:
        lines = existing_text.splitlines(keepends=True)
        out: list[str] = []
        i, replaced = 0, False
        while i < len(lines):
            if lines[i].strip() == header:
                out.append(block.lstrip("\n"))
                i += 1
                while i < len(lines) and not lines[i].lstrip().startswith("["):
                    i += 1
                replaced = True
                continue
            out.append(lines[i])
            i += 1
        new_text = "".join(out)
        action = "updated" if replaced else "added"
    else:
        new_text = (existing_text.rstrip() + block) if existing_text.strip() else block.lstrip("\n")
        action = "added"

    if new_text == existing_text:
        return InstallResult("Codex CLI", path, "unchanged", f"{server_key} already configured")

    path.write_text(new_text, encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return InstallResult("Codex CLI", path, action, f"{server_key} -> {url}")


# ---------------------------------------------------------------------------
# VS Code (user settings.json)
# ---------------------------------------------------------------------------
def vscode_settings_path() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Code" / "User" / "settings.json"
    if sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(appdata) / "Code" / "User" / "settings.json"
    xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(xdg) / "Code" / "User" / "settings.json"


def install_vscode(
    *,
    url: str | None = None,
    server_key: str = SERVER_KEY,
    config_path: Path | None = None,
) -> InstallResult:
    """Add to VS Code user settings under `mcp.servers.<name>`.

    Format used by the GitHub Copilot Chat MCP integration and other VS Code
    MCP clients (settings key `mcp.servers`):
        {"type": "http", "url": "..."}
    """
    url = url or _default_url()
    path = config_path or vscode_settings_path()
    config = _read_json(path)

    desired = {"type": "http", "url": url}
    existing = _get_nested(config, ["mcp", "servers", server_key])

    if existing == desired:
        return InstallResult("VS Code", path, "unchanged", f"{server_key} already configured")

    action = "updated" if existing else "added"
    _set_nested(config, ["mcp", "servers", server_key], desired)
    _atomic_write_json(path, config)
    return InstallResult("VS Code", path, action, f"{server_key} -> {url}")


def uninstall_vscode(*, server_key: str = SERVER_KEY, config_path: Path | None = None) -> InstallResult:
    path = config_path or vscode_settings_path()
    config = _read_json(path)
    if _delete_nested(config, ["mcp", "servers", server_key]):
        _atomic_write_json(path, config)
        return InstallResult("VS Code", path, "removed", f"{server_key} removed")
    return InstallResult("VS Code", path, "unchanged", f"{server_key} was not present")


# ---------------------------------------------------------------------------
# Cursor
# ---------------------------------------------------------------------------
def cursor_config_path() -> Path:
    return Path.home() / ".cursor" / "mcp.json"


def install_cursor(
    *,
    url: str | None = None,
    server_key: str = SERVER_KEY,
    config_path: Path | None = None,
) -> InstallResult:
    """Add to Cursor's MCP config (~/.cursor/mcp.json).

    Cursor uses the same Claude Desktop-style schema for stdio servers and
    supports `url` directly for HTTP servers.
    """
    url = url or _default_url()
    path = config_path or cursor_config_path()
    config = _read_json(path)
    config.setdefault("mcpServers", {})

    desired = {"url": url}
    existing = config["mcpServers"].get(server_key)

    if existing == desired:
        return InstallResult("Cursor", path, "unchanged", f"{server_key} already configured")

    action = "updated" if existing else "added"
    config["mcpServers"][server_key] = desired
    _atomic_write_json(path, config)
    return InstallResult("Cursor", path, action, f"{server_key} -> {url}; restart Cursor")


def uninstall_cursor(*, server_key: str = SERVER_KEY, config_path: Path | None = None) -> InstallResult:
    path = config_path or cursor_config_path()
    config = _read_json(path)
    servers = config.get("mcpServers", {})
    if server_key in servers:
        del servers[server_key]
        _atomic_write_json(path, config)
        return InstallResult("Cursor", path, "removed", f"{server_key} removed")
    return InstallResult("Cursor", path, "unchanged", f"{server_key} was not present")


# ---------------------------------------------------------------------------
# Windsurf
# ---------------------------------------------------------------------------
def windsurf_config_path() -> Path:
    return Path.home() / ".codeium" / "windsurf" / "mcp_config.json"


def install_windsurf(
    *,
    url: str | None = None,
    server_key: str = SERVER_KEY,
    config_path: Path | None = None,
) -> InstallResult:
    """Add to Windsurf MCP config (~/.codeium/windsurf/mcp_config.json).

    Same schema as Claude Desktop. For HTTP servers, Windsurf >= 1.0
    supports `serverUrl`; older versions need the mcp-remote bridge.
    """
    url = url or _default_url()
    path = config_path or windsurf_config_path()
    config = _read_json(path)
    config.setdefault("mcpServers", {})

    desired = {"serverUrl": url}
    existing = config["mcpServers"].get(server_key)

    if existing == desired:
        return InstallResult("Windsurf", path, "unchanged", f"{server_key} already configured")

    action = "updated" if existing else "added"
    config["mcpServers"][server_key] = desired
    _atomic_write_json(path, config)
    return InstallResult("Windsurf", path, action, f"{server_key} -> {url}; restart Windsurf")


def uninstall_windsurf(*, server_key: str = SERVER_KEY, config_path: Path | None = None) -> InstallResult:
    path = config_path or windsurf_config_path()
    config = _read_json(path)
    servers = config.get("mcpServers", {})
    if server_key in servers:
        del servers[server_key]
        _atomic_write_json(path, config)
        return InstallResult("Windsurf", path, "removed", f"{server_key} removed")
    return InstallResult("Windsurf", path, "unchanged", f"{server_key} was not present")


# ---------------------------------------------------------------------------
# Registry — used by the `mcp-aemps install` (no subcommand) "all" path
# ---------------------------------------------------------------------------
ALL_INSTALLERS = {
    "claude-desktop": install_claude_desktop,
    "claude-code": install_claude_code,
    "codex": install_codex,
    "vscode": install_vscode,
    "cursor": install_cursor,
    "windsurf": install_windsurf,
}

ALL_UNINSTALLERS = {
    "claude-desktop": uninstall_claude_desktop,
    "claude-code": uninstall_claude_code,
    "vscode": uninstall_vscode,
    "cursor": uninstall_cursor,
    "windsurf": uninstall_windsurf,
}
