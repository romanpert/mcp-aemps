# app/installers.py
"""One-command installers for popular MCP-compatible clients.

Each installer is idempotent (running twice is a no-op), atomic (either the
write succeeds fully or not at all), and additive (preserves existing entries
in the user's config).

**Transport defaults (locked 2026-05-08).** Every installer defaults to
**stdio** with the canonical Anthropic-style auto-launch:

    {"command": "uvx", "args": ["mcp-aemps@latest", "stdio"]}

stdio is the only mode that "just works" — the host spawns ``uvx`` on
demand, ``uvx`` downloads + caches the package on first run, no
separately-running server, no port management. **HTTP is opt-in via
``transport="http"``** for shared-server / multi-user / observability
deployments where you actually run ``mcp-aemps up`` somewhere
reachable. Earlier versions defaulted most installers to HTTP +
``localhost:8765``, which silently broke unless the user knew to start
the server first — that bug surfaced as "Server disconnected /
ECONNREFUSED" with no actionable error.

Supported clients (config path · format quirks):

- Claude Desktop  · ``claude_desktop_config.json::mcpServers``
                    HTTP via ``npx mcp-remote`` bridge
- Claude Code     · ``claude mcp add`` CLI preferred, fallback to
                    ``~/.claude.json::mcpServers``
- Codex CLI       · ``~/.codex/config.toml::[mcp_servers.<name>]`` (TOML)
- VS Code         · **dedicated** ``<user-profile>/Code/User/mcp.json::servers``
                    (settings.json::mcp.servers is deprecated, post-2025-Q4
                    VS Code shows a banner asking users to migrate).
- Cursor          · ``~/.cursor/mcp.json::mcpServers`` (or `.cursor/mcp.json`
                    project-scoped)
- Windsurf        · ``~/.codeium/windsurf/mcp_config.json::mcpServers``
                    (HTTP uses ``serverUrl``, not ``url``)
- Zed             · settings.json ``context_servers`` (HTTP uses ``url``)
- Continue.dev    · ``~/.continue/config.yaml::mcpServers[]`` (YAML list,
                    each entry has ``type`` = stdio | streamable-http | sse
                    — NOT ``http`` which is invalid).
- JetBrains Junie · ``~/.junie/mcp.json::mcpServers``
- Antigravity     · ``~/.gemini/antigravity/mcp_config.json::mcpServers``
                    (Google's late-2025 agentic IDE; HTTP uses
                    ``serverUrl``, same convention as Windsurf)
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.runtime_state import resolve_default_url

SERVER_KEY = "mcp-aemps"

# Canonical stdio launcher for every installer. Single source of truth so
# version bumps to the package spec only happen in one place.
STDIO_COMMAND = "uvx"
STDIO_ARGS: tuple[str, ...] = ("mcp-aemps@latest", "stdio")


def _stdio_block() -> dict[str, Any]:
    """Return the minimal stdio entry shared by every JSON-based
    installer (Claude Desktop, Cursor, Windsurf, Zed, Continue, Junie,
    VS Code, Claude Code fallback). ``type: stdio`` is included
    explicitly because some clients (Continue, the new VS Code mcp.json)
    require it; clients that ignore it just keep it as a no-op key."""
    return {"type": "stdio", "command": STDIO_COMMAND, "args": list(STDIO_ARGS)}


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
    warnings: tuple[str, ...] = ()


def _check_command_on_path(command: str) -> str | None:
    """Return a human-readable warning if ``command`` is not on PATH,
    else ``None``. Used by every installer to surface missing
    prerequisites at install-time instead of at server-launch-time
    (when the host swallows the failure as a generic "Server
    disconnected"). Never blocks the install — the user might be
    configuring a machine where the tool is installed under a
    different alias or PATH gets refreshed later."""
    if shutil.which(command):
        return None
    install_hint = {
        "uvx": "Install uv: https://docs.astral.sh/uv/getting-started/installation/",
        "uv": "Install uv: https://docs.astral.sh/uv/getting-started/installation/",
        "npx": "Install Node.js (≥ 18): https://nodejs.org/en/download",
        "npm": "Install Node.js (≥ 18): https://nodejs.org/en/download",
        "pipx": "Install pipx: https://pipx.pypa.io/stable/installation/",
    }.get(command, "")
    suffix = f"  {install_hint}" if install_hint else ""
    return f"WARNING: '{command}' not found on PATH — config written but the client will fail to launch the server until you install it.{suffix}"


# Per-client install hints surfaced when the client itself doesn't
# appear to be installed (no config directory + no launcher on PATH).
# Keeping these centralised makes adding a new installer trivial:
# define the entry below + call ``_check_client_installed`` from the
# new installer.
_CLIENT_INSTALL_HINTS: dict[str, str] = {
    "Claude Desktop": "https://claude.ai/download",
    "Claude Code": "https://docs.claude.com/en/docs/claude-code/quickstart",
    "Codex CLI": "https://github.com/openai/codex",
    "VS Code": "https://code.visualstudio.com/download",
    "Cursor": "https://cursor.com/download",
    "Windsurf": "https://codeium.com/windsurf",
    "Zed": "https://zed.dev/download",
    "Continue.dev": "https://www.continue.dev/",
    "JetBrains Junie": "https://www.jetbrains.com/junie/",
    "Antigravity": "https://antigravity.google/",
}


def _collect_install_warnings(
    client_name: str,
    *,
    config_dirs: tuple[Path, ...] = (),
    path_binaries: tuple[str, ...] = (),
    extra_commands: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """One-call wrapper used at the top of every ``install_<client>``.

    Returns the combined warnings tuple to feed straight into
    ``InstallResult(warnings=...)``:
    - Client-installed-or-not detection (NOTE).
    - Command prerequisites on PATH (WARNING). Pass ``extra_commands``
      with the launchers the chosen transport will spawn (e.g.
      ``("uvx",)`` for stdio, ``("npx",)`` for the mcp-remote bridge)."""
    out: list[str] = []
    if w := _check_client_installed(client_name, config_dirs=config_dirs, path_binaries=path_binaries):
        out.append(w)
    for cmd in extra_commands:
        if w := _check_command_on_path(cmd):
            out.append(w)
    return tuple(out)


def _check_client_installed(
    client_name: str,
    *,
    config_dirs: tuple[Path, ...] = (),
    path_binaries: tuple[str, ...] = (),
) -> str | None:
    """Return a NOTE warning if the target client doesn't appear to be
    installed, else ``None``.

    Detection is deliberately permissive — false negatives (warning
    when client is actually installed elsewhere) are far worse than
    false positives. The check is True if **any** of:
    - any directory in ``config_dirs`` exists (the client created its
      profile, has been launched at least once);
    - any binary in ``path_binaries`` resolves on PATH (CLI tools).

    NEVER blocks the install — the user may be deliberately
    pre-configuring the machine before installing the client."""
    if any(d.exists() for d in config_dirs):
        return None
    if any(shutil.which(b) for b in path_binaries):
        return None

    hint = _CLIENT_INSTALL_HINTS.get(client_name, "")
    suffix = f"  Install: {hint}" if hint else ""
    paths = ", ".join(str(d) for d in config_dirs) or "<no path heuristic>"
    return (
        f"NOTE: {client_name} doesn't appear to be installed (no profile "
        f"directory at: {paths}). Config has been written for when you "
        f"install it.{suffix}"
    )


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
    transport: str = "stdio",
) -> InstallResult:
    """Add or update the mcp-aemps entry in claude_desktop_config.json.

    Two transport modes:

    - **stdio** (default, Anthropic-canonical): Claude Desktop launches
      `uvx mcp-aemps stdio` on demand. No long-running HTTP server, no
      port management, no extra bridge. This is the pattern Anthropic
      ships its reference servers with.
    - **http**: bridges stdio↔HTTP via `npx mcp-remote <url>`. Use this
      when you already run the server yourself (e.g. shared in your
      network) and want the client to connect remotely.
    """
    path = config_path or claude_desktop_config_path()
    config = _read_json(path)
    config.setdefault("mcpServers", {})

    warnings: list[str] = []

    if w := _check_client_installed("Claude Desktop", config_dirs=(path.parent,)):
        warnings.append(w)

    if transport == "stdio":
        desired: dict[str, Any] = {"command": "uvx", "args": ["mcp-aemps@latest", "stdio"]}
        message_suffix = "(uvx auto-launch); restart Claude Desktop"
        if w := _check_command_on_path("uvx"):
            warnings.append(w)
    else:
        url = url or _default_url()
        desired = {"command": "npx", "args": ["-y", "mcp-remote", url]}
        message_suffix = f"-> {url} (mcp-remote bridge); restart Claude Desktop"
        if w := _check_command_on_path("npx"):
            warnings.append(w)
        # mcp-remote bridges to a server you must run yourself —
        # without it, the bridge fails with ECONNREFUSED at launch.
        warnings.append(
            f"NOTE: http transport requires a running server at {url} "
            f"(start it with `mcp-aemps up`). The stdio transport "
            f"(default) does not need a separate server."
        )

    existing = config["mcpServers"].get(server_key)
    if existing == desired:
        return InstallResult(
            "Claude Desktop",
            path,
            "unchanged",
            f"{server_key} already configured",
            warnings=tuple(warnings),
        )

    action = "updated" if existing else "added"
    config["mcpServers"][server_key] = desired
    _atomic_write_json(path, config)
    return InstallResult(
        "Claude Desktop",
        path,
        action,
        f"{server_key} {message_suffix}",
        warnings=tuple(warnings),
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
    transport: str = "stdio",
) -> InstallResult:
    """Register mcp-aemps with Claude Code. CLI-preferred, JSON fallback.

    Defaults to stdio (``claude mcp add --transport stdio mcp-aemps -- uvx
    mcp-aemps@latest stdio``). HTTP opt-in via ``transport="http"`` for
    when a separately-running server is reachable.
    """
    warnings = _collect_install_warnings(
        "Claude Code",
        config_dirs=(Path.home() / ".claude",),
        path_binaries=("claude",),
    )

    if transport == "stdio":
        # claude mcp add CLI form. The `--` separator passes the rest
        # to uvx unmodified, exactly like claude code's docs example.
        cli_cmd = [
            "claude",
            "mcp",
            "add",
            "--scope",
            scope,
            "--transport",
            "stdio",
            server_key,
            "--",
            STDIO_COMMAND,
            *STDIO_ARGS,
        ]
        json_desired: dict[str, Any] = _stdio_block()
        message_target = "(uvx auto-launch)"
        if w := _check_command_on_path(STDIO_COMMAND):
            warnings = (*warnings, w)
    else:
        url = url or _default_url()
        cli_cmd = [
            "claude",
            "mcp",
            "add",
            "--scope",
            scope,
            "--transport",
            "http",
            server_key,
            url,
        ]
        json_desired = {"type": "http", "url": url}
        message_target = f"-> {url}"
        warnings = (
            *warnings,
            f"NOTE: http transport requires a running server at {url}.",
        )

    cli_allowed = config_path is None and (use_cli is None or use_cli)
    if cli_allowed and _claude_cli_available():
        try:
            result = subprocess.run(cli_cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                return InstallResult(
                    "Claude Code",
                    Path("(via `claude mcp add`)"),
                    "added",
                    f"{server_key} {message_target} (scope={scope})",
                    warnings=warnings,
                )
            stderr = (result.stderr or "").lower()
            if "already exists" in stderr or "already configured" in stderr:
                return InstallResult(
                    "Claude Code",
                    Path("(via `claude mcp add`)"),
                    "unchanged",
                    f"{server_key} already configured",
                    warnings=warnings,
                )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    path = config_path or claude_code_config_path()
    config = _read_json(path)
    config.setdefault("mcpServers", {})
    desired = json_desired
    existing = config["mcpServers"].get(server_key)

    if existing == desired:
        return InstallResult(
            "Claude Code", path, "unchanged", f"{server_key} already configured", warnings=warnings
        )

    action = "updated" if existing else "added"
    config["mcpServers"][server_key] = desired
    _atomic_write_json(path, config)
    return InstallResult("Claude Code", path, action, f"{server_key} {message_target}", warnings=warnings)


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
    transport: str = "stdio",
) -> InstallResult:
    """Append a [mcp_servers.<name>] block to ~/.codex/config.toml.

    Defaults to stdio with the canonical launcher. HTTP opt-in via
    ``transport="http"``.
    """
    path = config_path or codex_config_path()
    warnings = _collect_install_warnings(
        "Codex CLI",
        config_dirs=(path.parent,),
        path_binaries=("codex",),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_text = path.read_text(encoding="utf-8") if path.exists() else ""

    if transport == "stdio":
        # TOML rendering of the stdio block. ``args`` is a TOML array of
        # strings; ``command`` is a quoted string. Both line-by-line so
        # the file diffs cleanly across version bumps.
        args_toml = ", ".join(f'"{a}"' for a in STDIO_ARGS)
        block = f'\n[mcp_servers.{server_key}]\ncommand = "{STDIO_COMMAND}"\nargs = [{args_toml}]\n'
        message_target = f"{STDIO_COMMAND} {' '.join(STDIO_ARGS)} (stdio)"
        if w := _check_command_on_path(STDIO_COMMAND):
            warnings = (*warnings, w)
    else:
        url = url or _default_url()
        block = f'\n[mcp_servers.{server_key}]\nurl = "{url}"\ntransport = "http"\n'
        message_target = f"-> {url}"
        warnings = (
            *warnings,
            f"NOTE: http transport requires a running server at {url} (start it with `mcp-aemps up`).",
        )

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
        return InstallResult(
            "Codex CLI", path, "unchanged", f"{server_key} already configured", warnings=warnings
        )

    path.write_text(new_text, encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return InstallResult("Codex CLI", path, action, f"{server_key} {message_target}", warnings=warnings)


def uninstall_codex(*, server_key: str = SERVER_KEY, config_path: Path | None = None) -> InstallResult:
    """Remove the [mcp_servers.<server_key>] block from ~/.codex/config.toml."""
    path = config_path or codex_config_path()
    if not path.exists():
        return InstallResult("Codex CLI", path, "unchanged", f"{server_key} was not present")

    text = path.read_text(encoding="utf-8")
    header = f"[mcp_servers.{server_key}]"
    if header not in text:
        return InstallResult("Codex CLI", path, "unchanged", f"{server_key} was not present")

    lines = text.splitlines(keepends=True)
    out: list[str] = []
    i = 0
    while i < len(lines):
        if lines[i].strip() == header:
            i += 1
            while i < len(lines) and not lines[i].lstrip().startswith("["):
                i += 1
            # also drop a trailing blank line if any
            while out and out[-1].strip() == "":
                out.pop()
            if out:
                out.append("\n")
            continue
        out.append(lines[i])
        i += 1
    new_text = "".join(out).lstrip("\n")
    path.write_text(new_text, encoding="utf-8")
    return InstallResult("Codex CLI", path, "removed", f"{server_key} removed")


# ---------------------------------------------------------------------------
# VS Code (dedicated mcp.json — NOT settings.json::mcp.servers)
# ---------------------------------------------------------------------------
# As of late 2025 VS Code surfaces an explicit deprecation banner when MCP
# servers are configured in settings.json::mcp.servers and asks users to
# migrate to a dedicated ``mcp.json`` file. We always write the new
# location now; the old code path is removed entirely so we don't keep
# resurrecting deprecation warnings on every reinstall.


def vscode_user_mcp_path() -> Path:
    """Per-user dedicated MCP config (post-2025 standard)."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Code" / "User" / "mcp.json"
    if sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(appdata) / "Code" / "User" / "mcp.json"
    xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(xdg) / "Code" / "User" / "mcp.json"


def vscode_legacy_settings_path() -> Path:
    """Old settings.json location — only used for opportunistic cleanup
    of the deprecated ``mcp.servers`` block on uninstall."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Code" / "User" / "settings.json"
    if sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(appdata) / "Code" / "User" / "settings.json"
    xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(xdg) / "Code" / "User" / "settings.json"


# Kept as an alias so external callers / tests using ``vscode_settings_path``
# don't break — points at the new dedicated mcp.json now.
vscode_settings_path = vscode_user_mcp_path


def install_vscode(
    *,
    url: str | None = None,
    server_key: str = SERVER_KEY,
    config_path: Path | None = None,
    transport: str = "stdio",
) -> InstallResult:
    """Add to VS Code's dedicated ``mcp.json`` under ``servers.<name>``.

    Schema (post-2025 VS Code):

        {"servers": {"<name>": {"type": "stdio"|"http", ...}}}

    Defaults to stdio; pass ``transport="http"`` for shared deployments.
    """
    path = config_path or vscode_user_mcp_path()
    warnings = _collect_install_warnings(
        "VS Code",
        config_dirs=(path.parent,),
        path_binaries=("code",),
    )

    # Opportunistic migration: if the legacy settings.json had a stale
    # ``mcp.servers.<name>`` entry, drop it on install so the user
    # doesn't see VS Code's deprecation banner anymore.
    if config_path is None:
        legacy_path = vscode_legacy_settings_path()
        if legacy_path.exists():
            legacy = _read_json(legacy_path)
            if _delete_nested(legacy, ["mcp", "servers", server_key]):
                _atomic_write_json(legacy_path, legacy)
                warnings = (
                    *warnings,
                    f"NOTE: removed deprecated entry from {legacy_path} "
                    f"(VS Code now uses dedicated mcp.json).",
                )

    config = _read_json(path)
    config.setdefault("servers", {})

    if transport == "stdio":
        desired: dict[str, Any] = _stdio_block()
        message_suffix = "(uvx auto-launch); restart VS Code"
        if w := _check_command_on_path(STDIO_COMMAND):
            warnings = (*warnings, w)
    else:
        url = url or _default_url()
        desired = {"type": "http", "url": url}
        message_suffix = f"-> {url}; restart VS Code"
        warnings = (
            *warnings,
            f"NOTE: http transport requires a running server at {url} (start it with `mcp-aemps up`).",
        )

    existing = config["servers"].get(server_key)
    if existing == desired:
        return InstallResult(
            "VS Code", path, "unchanged", f"{server_key} already configured", warnings=warnings
        )

    action = "updated" if existing else "added"
    config["servers"][server_key] = desired
    _atomic_write_json(path, config)
    return InstallResult("VS Code", path, action, f"{server_key} {message_suffix}", warnings=warnings)


def uninstall_vscode(*, server_key: str = SERVER_KEY, config_path: Path | None = None) -> InstallResult:
    path = config_path or vscode_user_mcp_path()

    # Clean both locations: the new mcp.json (authoritative) and the
    # legacy settings.json (in case the user installed with an older
    # mcp-aemps version).
    removed_anywhere = False
    config = _read_json(path)
    servers = config.get("servers") or {}
    if server_key in servers:
        del servers[server_key]
        _atomic_write_json(path, config)
        removed_anywhere = True

    if config_path is None:
        legacy_path = vscode_legacy_settings_path()
        if legacy_path.exists():
            legacy = _read_json(legacy_path)
            if _delete_nested(legacy, ["mcp", "servers", server_key]):
                _atomic_write_json(legacy_path, legacy)
                removed_anywhere = True

    if removed_anywhere:
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
    transport: str = "stdio",
) -> InstallResult:
    """Add to Cursor's MCP config (~/.cursor/mcp.json).

    Defaults to stdio with the canonical ``uvx mcp-aemps@latest stdio``
    launcher. Pass ``transport="http"`` (with explicit ``url=``) for
    shared-server deployments.
    """
    path = config_path or cursor_config_path()
    warnings = _collect_install_warnings(
        "Cursor",
        config_dirs=(path.parent,),
        path_binaries=("cursor",),
    )
    config = _read_json(path)
    config.setdefault("mcpServers", {})

    if transport == "stdio":
        desired: dict[str, Any] = _stdio_block()
        message_suffix = "(uvx auto-launch); restart Cursor"
        if w := _check_command_on_path(STDIO_COMMAND):
            warnings = (*warnings, w)
    else:
        url = url or _default_url()
        desired = {"url": url}
        message_suffix = f"-> {url}; restart Cursor"
        warnings = (
            *warnings,
            f"NOTE: http transport requires a running server at {url} (start it with `mcp-aemps up`).",
        )

    existing = config["mcpServers"].get(server_key)

    if existing == desired:
        return InstallResult(
            "Cursor", path, "unchanged", f"{server_key} already configured", warnings=warnings
        )

    action = "updated" if existing else "added"
    config["mcpServers"][server_key] = desired
    _atomic_write_json(path, config)
    return InstallResult("Cursor", path, action, f"{server_key} {message_suffix}", warnings=warnings)


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
    transport: str = "stdio",
) -> InstallResult:
    """Add to Windsurf MCP config (~/.codeium/windsurf/mcp_config.json).

    Defaults to stdio with the canonical ``uvx mcp-aemps@latest stdio``
    launcher. For HTTP, Windsurf uses the field name ``serverUrl``
    (not ``url`` — distinct from every other client).
    """
    path = config_path or windsurf_config_path()
    warnings = _collect_install_warnings(
        "Windsurf",
        config_dirs=(path.parent,),
        path_binaries=("windsurf",),
    )
    config = _read_json(path)
    config.setdefault("mcpServers", {})

    if transport == "stdio":
        desired: dict[str, Any] = _stdio_block()
        message_suffix = "(uvx auto-launch); restart Windsurf"
        if w := _check_command_on_path(STDIO_COMMAND):
            warnings = (*warnings, w)
    else:
        url = url or _default_url()
        desired = {"serverUrl": url}
        message_suffix = f"-> {url}; restart Windsurf"
        warnings = (
            *warnings,
            f"NOTE: http transport requires a running server at {url} (start it with `mcp-aemps up`).",
        )

    existing = config["mcpServers"].get(server_key)

    if existing == desired:
        return InstallResult(
            "Windsurf", path, "unchanged", f"{server_key} already configured", warnings=warnings
        )

    action = "updated" if existing else "added"
    config["mcpServers"][server_key] = desired
    _atomic_write_json(path, config)
    return InstallResult("Windsurf", path, action, f"{server_key} {message_suffix}", warnings=warnings)


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
# Zed
# ---------------------------------------------------------------------------
def zed_settings_path() -> Path:
    if sys.platform == "darwin":
        return Path.home() / ".config" / "zed" / "settings.json"
    if sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(appdata) / "Zed" / "settings.json"
    xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(xdg) / "zed" / "settings.json"


def install_zed(
    *,
    url: str | None = None,
    server_key: str = SERVER_KEY,
    config_path: Path | None = None,
    transport: str = "stdio",
) -> InstallResult:
    """Add to Zed's user settings under ``context_servers.<name>``.

    Defaults to stdio with the canonical launcher. Zed expects an
    explicit ``env: {}`` field on stdio entries (the schema requires the
    key even when empty); HTTP entries use ``url``.
    """
    path = config_path or zed_settings_path()
    warnings = _collect_install_warnings(
        "Zed",
        config_dirs=(path.parent,),
        path_binaries=("zed",),
    )
    config = _read_json(path)

    if transport == "stdio":
        # Zed validates the shape of ``env`` even when empty. Drop the
        # ``type`` key the other clients accept — Zed's schema rejects
        # unknown keys on context_servers entries.
        desired: dict[str, Any] = {
            "command": STDIO_COMMAND,
            "args": list(STDIO_ARGS),
            "env": {},
        }
        message_suffix = "(uvx auto-launch); restart Zed"
        if w := _check_command_on_path(STDIO_COMMAND):
            warnings = (*warnings, w)
    else:
        url = url or _default_url()
        desired = {"url": url}
        message_suffix = f"-> {url}; restart Zed"
        warnings = (
            *warnings,
            f"NOTE: http transport requires a running server at {url} (start it with `mcp-aemps up`).",
        )

    existing = _get_nested(config, ["context_servers", server_key])

    if existing == desired:
        return InstallResult("Zed", path, "unchanged", f"{server_key} already configured", warnings=warnings)

    action = "updated" if existing else "added"
    _set_nested(config, ["context_servers", server_key], desired)
    _atomic_write_json(path, config)
    return InstallResult("Zed", path, action, f"{server_key} {message_suffix}", warnings=warnings)


def uninstall_zed(*, server_key: str = SERVER_KEY, config_path: Path | None = None) -> InstallResult:
    path = config_path or zed_settings_path()
    config = _read_json(path)
    if _delete_nested(config, ["context_servers", server_key]):
        _atomic_write_json(path, config)
        return InstallResult("Zed", path, "removed", f"{server_key} removed")
    return InstallResult("Zed", path, "unchanged", f"{server_key} was not present")


# ---------------------------------------------------------------------------
# Continue.dev
# ---------------------------------------------------------------------------
def continue_config_path() -> Path:
    return Path.home() / ".continue" / "config.yaml"


_CONTINUE_BLOCK_HEADER = "# --- mcp-aemps (managed by `mcp-aemps install continue`) ---"
_CONTINUE_BLOCK_FOOTER = "# --- end mcp-aemps ---"


def _build_continue_stdio_block(server_key: str) -> str:
    args_yaml = "\n".join(f'      - "{a}"' for a in STDIO_ARGS)
    return (
        f"{_CONTINUE_BLOCK_HEADER}\n"
        f"mcpServers:\n"
        f"  - name: {server_key}\n"
        f"    type: stdio\n"
        f"    command: {STDIO_COMMAND}\n"
        f"    args:\n"
        f"{args_yaml}\n"
        f"{_CONTINUE_BLOCK_FOOTER}\n"
    )


def _build_continue_http_block(server_key: str, url: str) -> str:
    # Continue.dev's valid type values for HTTP are ``streamable-http``
    # or ``sse`` — ``http`` (which earlier mcp-aemps versions wrote) is
    # NOT in the schema and silently no-ops on Continue.
    return (
        f"{_CONTINUE_BLOCK_HEADER}\n"
        f"mcpServers:\n"
        f"  - name: {server_key}\n"
        f"    type: streamable-http\n"
        f"    url: {url}\n"
        f"{_CONTINUE_BLOCK_FOOTER}\n"
    )


def install_continue(
    *,
    url: str | None = None,
    server_key: str = SERVER_KEY,
    config_path: Path | None = None,
    transport: str = "stdio",
) -> InstallResult:
    """Append a managed mcp-aemps block to ~/.continue/config.yaml.

    Continue.dev (VS Code & JetBrains extension) reads ``mcpServers`` as
    a YAML list. Each entry needs ``type`` ∈ {``stdio``,
    ``streamable-http``, ``sse``} — ``http`` (the value earlier
    mcp-aemps versions wrote) is **not** in Continue's schema and the
    block silently no-ops. We default to stdio; HTTP entries use
    ``streamable-http``. Block is fenced with sentinel comments so
    re-runs replace exactly our block.
    """
    path = config_path or continue_config_path()
    warnings = _collect_install_warnings(
        "Continue.dev",
        config_dirs=(path.parent,),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_text = path.read_text(encoding="utf-8") if path.exists() else ""

    if transport == "stdio":
        block = _build_continue_stdio_block(server_key)
        message_target = "(uvx auto-launch)"
        if w := _check_command_on_path(STDIO_COMMAND):
            warnings = (*warnings, w)
    else:
        url = url or _default_url()
        block = _build_continue_http_block(server_key, url)
        message_target = f"-> {url}"
        warnings = (
            *warnings,
            f"NOTE: http transport requires a running server at {url}.",
        )

    if _CONTINUE_BLOCK_HEADER in existing_text:
        # Replace the existing managed block in place.
        before, _, rest = existing_text.partition(_CONTINUE_BLOCK_HEADER)
        _, _, after = rest.partition(_CONTINUE_BLOCK_FOOTER)
        new_text = before.rstrip() + ("\n\n" if before.strip() else "") + block + after.lstrip("\n")
        action = "updated" if existing_text.strip() != new_text.strip() else "unchanged"
    else:
        sep = "\n\n" if existing_text.strip() else ""
        new_text = existing_text.rstrip("\n") + sep + block
        action = "added"

    if new_text == existing_text:
        return InstallResult(
            "Continue.dev", path, "unchanged", f"{server_key} already configured", warnings=warnings
        )

    path.write_text(new_text, encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return InstallResult(
        "Continue.dev",
        path,
        action,
        f"{server_key} {message_target}; restart your IDE",
        warnings=warnings,
    )


def uninstall_continue(*, server_key: str = SERVER_KEY, config_path: Path | None = None) -> InstallResult:
    path = config_path or continue_config_path()
    if not path.exists():
        return InstallResult("Continue.dev", path, "unchanged", f"{server_key} was not present")

    text = path.read_text(encoding="utf-8")
    if _CONTINUE_BLOCK_HEADER not in text:
        return InstallResult("Continue.dev", path, "unchanged", f"{server_key} was not present")

    before, _, rest = text.partition(_CONTINUE_BLOCK_HEADER)
    _, _, after = rest.partition(_CONTINUE_BLOCK_FOOTER)
    new_text = (before.rstrip("\n") + "\n" + after.lstrip("\n")).rstrip("\n") + "\n"
    if not new_text.strip():
        new_text = ""
    path.write_text(new_text, encoding="utf-8")
    return InstallResult("Continue.dev", path, "removed", f"{server_key} removed")


# ---------------------------------------------------------------------------
# JetBrains Junie / AI Assistant
# ---------------------------------------------------------------------------
def jetbrains_config_path() -> Path:
    """JetBrains Junie reads ~/.junie/mcp.json (standard MCP JSON schema).

    AI Assistant in JetBrains 2025.x stores MCP servers in per-IDE XML
    files (``<config-dir>/options/mcp-server.xml``); editing those is
    fragile across IDE versions, so we target Junie's stable JSON path
    and surface a hint to use the Settings UI for AI Assistant.
    """
    return Path.home() / ".junie" / "mcp.json"


def install_jetbrains(
    *,
    url: str | None = None,
    server_key: str = SERVER_KEY,
    config_path: Path | None = None,
    transport: str = "stdio",
) -> InstallResult:
    """Add to JetBrains Junie's MCP config (~/.junie/mcp.json).

    Defaults to stdio. For the classic AI Assistant plugin (not Junie),
    configure manually: Settings → Tools → AI Assistant → MCP servers.
    """
    path = config_path or jetbrains_config_path()
    warnings = _collect_install_warnings(
        "JetBrains Junie",
        config_dirs=(path.parent,),
    )
    config = _read_json(path)
    config.setdefault("mcpServers", {})

    if transport == "stdio":
        desired: dict[str, Any] = _stdio_block()
        message_target = "(uvx auto-launch)"
        if w := _check_command_on_path(STDIO_COMMAND):
            warnings = (*warnings, w)
    else:
        url = url or _default_url()
        desired = {"type": "http", "url": url}
        message_target = f"-> {url}"
        warnings = (
            *warnings,
            f"NOTE: http transport requires a running server at {url}.",
        )

    existing = config["mcpServers"].get(server_key)

    if existing == desired:
        return InstallResult(
            "JetBrains Junie",
            path,
            "unchanged",
            f"{server_key} already configured",
            warnings=warnings,
        )

    action = "updated" if existing else "added"
    config["mcpServers"][server_key] = desired
    _atomic_write_json(path, config)
    return InstallResult(
        "JetBrains Junie",
        path,
        action,
        f"{server_key} {message_target}; restart your JetBrains IDE "
        "(AI Assistant users: configure via Settings -> Tools -> AI Assistant -> MCP servers)",
        warnings=warnings,
    )


def uninstall_jetbrains(*, server_key: str = SERVER_KEY, config_path: Path | None = None) -> InstallResult:
    path = config_path or jetbrains_config_path()
    config = _read_json(path)
    servers = config.get("mcpServers", {})
    if server_key in servers:
        del servers[server_key]
        _atomic_write_json(path, config)
        return InstallResult("JetBrains Junie", path, "removed", f"{server_key} removed")
    return InstallResult("JetBrains Junie", path, "unchanged", f"{server_key} was not present")


# ---------------------------------------------------------------------------
# Google Antigravity
# ---------------------------------------------------------------------------
# Antigravity is Google's late-2025 agentic IDE. MCP config lives under
# the gemini config tree, NOT alongside other IDE configs. Schema is
# the standard ``mcpServers`` envelope used by Cursor / Windsurf / Junie,
# but with one Antigravity-specific quirk shared with Windsurf: HTTP
# entries use ``serverUrl`` (not ``url``). Verified against the
# upstream guidance at
# https://github.com/github/github-mcp-server/blob/main/docs/installation-guides/install-antigravity.md
# (2026-01).


def antigravity_config_path() -> Path:
    """Antigravity MCP config — cross-platform per Path.home().

    macOS / Linux: ``~/.gemini/antigravity/mcp_config.json``
    Windows:       ``C:\\Users\\<USER>\\.gemini\\antigravity\\mcp_config.json``
    """
    return Path.home() / ".gemini" / "antigravity" / "mcp_config.json"


def install_antigravity(
    *,
    url: str | None = None,
    server_key: str = SERVER_KEY,
    config_path: Path | None = None,
    transport: str = "stdio",
) -> InstallResult:
    """Add to Antigravity's MCP config (``~/.gemini/antigravity/mcp_config.json``).

    Defaults to stdio with the canonical launcher. Antigravity reloads
    the config automatically after save — no IDE restart needed (per
    Google's docs).
    """
    path = config_path or antigravity_config_path()
    warnings = _collect_install_warnings(
        "Antigravity",
        config_dirs=(path.parent, Path.home() / ".gemini"),
        path_binaries=("antigravity",),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    config = _read_json(path)
    config.setdefault("mcpServers", {})

    if transport == "stdio":
        desired: dict[str, Any] = _stdio_block()
        message_target = "(uvx auto-launch)"
        if w := _check_command_on_path(STDIO_COMMAND):
            warnings = (*warnings, w)
    else:
        url = url or _default_url()
        # Antigravity uses ``serverUrl`` (same convention as Windsurf).
        desired = {"serverUrl": url}
        message_target = f"-> {url}"
        warnings = (
            *warnings,
            f"NOTE: http transport requires a running server at {url}.",
        )

    existing = config["mcpServers"].get(server_key)

    if existing == desired:
        return InstallResult(
            "Antigravity", path, "unchanged", f"{server_key} already configured", warnings=warnings
        )

    action = "updated" if existing else "added"
    config["mcpServers"][server_key] = desired
    _atomic_write_json(path, config)
    return InstallResult(
        "Antigravity",
        path,
        action,
        f"{server_key} {message_target} (Antigravity reloads automatically)",
        warnings=warnings,
    )


def uninstall_antigravity(*, server_key: str = SERVER_KEY, config_path: Path | None = None) -> InstallResult:
    path = config_path or antigravity_config_path()
    config = _read_json(path)
    servers = config.get("mcpServers", {})
    if server_key in servers:
        del servers[server_key]
        _atomic_write_json(path, config)
        return InstallResult("Antigravity", path, "removed", f"{server_key} removed")
    return InstallResult("Antigravity", path, "unchanged", f"{server_key} was not present")


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
    "zed": install_zed,
    "continue": install_continue,
    "jetbrains": install_jetbrains,
    "antigravity": install_antigravity,
}

ALL_UNINSTALLERS = {
    "claude-desktop": uninstall_claude_desktop,
    "claude-code": uninstall_claude_code,
    "codex": uninstall_codex,
    "vscode": uninstall_vscode,
    "cursor": uninstall_cursor,
    "windsurf": uninstall_windsurf,
    "zed": uninstall_zed,
    "continue": uninstall_continue,
    "jetbrains": uninstall_jetbrains,
    "antigravity": uninstall_antigravity,
}
