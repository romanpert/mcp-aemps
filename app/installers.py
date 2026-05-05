# app/installers.py
"""One-command installers for popular MCP-compatible clients.

Each installer is idempotent: running twice produces the same result. They
edit the user's existing config file (preserving other entries) instead of
overwriting it. All paths are resolved per-platform.

Supported clients:
- Claude Desktop  (macOS / Windows / Linux)
- Claude Code     (CLI command preferred, fallback to ~/.claude.json edit)
- OpenAI Codex    (~/.codex/config.toml or environment-driven config)
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

SERVER_KEY = "mcp-aemps"
DEFAULT_URL = "http://localhost:8000/mcp"


# ---------------------------------------------------------------------------
# Common
# ---------------------------------------------------------------------------
@dataclass
class InstallResult:
    client: str
    config_path: Path
    action: str  # "added" | "updated" | "unchanged"
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
    # linux + others
    xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(xdg) / "Claude" / "claude_desktop_config.json"


def install_claude_desktop(
    *,
    url: str = DEFAULT_URL,
    server_key: str = SERVER_KEY,
    config_path: Path | None = None,
) -> InstallResult:
    """Add or update the mcp-aemps entry in claude_desktop_config.json.

    Newer Claude Desktop versions (>= 0.7) support remote MCP servers via
    `url`. We use that — no `mcp-proxy` shim required.
    """
    path = config_path or claude_desktop_config_path()
    config = _read_json(path)
    config.setdefault("mcpServers", {})

    desired = {"url": url}
    existing = config["mcpServers"].get(server_key)

    if existing == desired:
        return InstallResult("Claude Desktop", path, "unchanged", f"{server_key} already configured")

    action = "updated" if existing else "added"
    config["mcpServers"][server_key] = desired
    _atomic_write_json(path, config)
    return InstallResult(
        "Claude Desktop", path, action, f"{server_key} -> {url}; restart Claude Desktop to apply"
    )


# ---------------------------------------------------------------------------
# Claude Code
# ---------------------------------------------------------------------------
def claude_code_config_path() -> Path:
    """Resolve the Claude Code user config path."""
    return Path.home() / ".claude.json"


def _claude_cli_available() -> bool:
    return shutil.which("claude") is not None


def install_claude_code(
    *,
    url: str = DEFAULT_URL,
    server_key: str = SERVER_KEY,
    scope: str = "user",
    config_path: Path | None = None,
    use_cli: bool | None = None,
) -> InstallResult:
    """Register mcp-aemps with Claude Code.

    Preferred path: `claude mcp add --transport http <name> <url>` if the
    Claude Code CLI is available (handles validation, scopes, and lockfile).
    Fallback: edit ~/.claude.json directly with the same effect.

    When `config_path` is provided explicitly, the file edit path is used —
    this prevents tests from accidentally touching the user's real config.
    Set `use_cli=False` to force the fallback even without `config_path`.
    """
    cli_allowed = config_path is None and (use_cli is None or use_cli)
    if cli_allowed and _claude_cli_available():
        try:
            cmd = [
                "claude", "mcp", "add",
                "--scope", scope,
                "--transport", "http",
                server_key,
                url,
            ]
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


# ---------------------------------------------------------------------------
# OpenAI Codex CLI
# ---------------------------------------------------------------------------
def codex_config_path() -> Path:
    return Path.home() / ".codex" / "config.toml"


def install_codex(
    *,
    url: str = DEFAULT_URL,
    server_key: str = SERVER_KEY,
    config_path: Path | None = None,
) -> InstallResult:
    """Append a [mcp_servers.<name>] block to ~/.codex/config.toml.

    Codex CLI uses TOML. We append in idempotent mode: if a block with the
    same name and URL already exists, do nothing; otherwise either replace
    the existing block or append a new one.
    """
    path = config_path or codex_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_text = path.read_text(encoding="utf-8") if path.exists() else ""

    block = (
        f"\n[mcp_servers.{server_key}]\n"
        f'url = "{url}"\n'
        f'transport = "http"\n'
    )
    header = f"[mcp_servers.{server_key}]"

    if header in existing_text:
        # Replace the existing block (everything from header to next [section] or EOF)
        lines = existing_text.splitlines(keepends=True)
        out: list[str] = []
        i = 0
        replaced = False
        while i < len(lines):
            if lines[i].strip() == header:
                # consume until next [section] header
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
# Uninstallers
# ---------------------------------------------------------------------------
def uninstall_claude_desktop(*, server_key: str = SERVER_KEY, config_path: Path | None = None) -> InstallResult:
    path = config_path or claude_desktop_config_path()
    config = _read_json(path)
    servers = config.get("mcpServers", {})
    if server_key in servers:
        del servers[server_key]
        _atomic_write_json(path, config)
        return InstallResult("Claude Desktop", path, "removed", f"{server_key} removed")
    return InstallResult("Claude Desktop", path, "unchanged", f"{server_key} was not present")


def uninstall_claude_code(
    *, server_key: str = SERVER_KEY, config_path: Path | None = None, use_cli: bool | None = None,
) -> InstallResult:
    cli_allowed = config_path is None and (use_cli is None or use_cli)
    if cli_allowed and _claude_cli_available():
        try:
            result = subprocess.run(
                ["claude", "mcp", "remove", server_key],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                return InstallResult("Claude Code", Path("(via `claude mcp remove`)"), "removed", f"{server_key} removed")
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
