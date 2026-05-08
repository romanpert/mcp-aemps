# app/migration_check.py
"""Detect mcp-aemps client configs that reference legacy defaults.

Scans the configured config-file paths of every supported MCP client
for known-bad legacy patterns (e.g. the pre-v0.2 default port
``localhost:8000``) **inside** our own server entry. Returns a list
of stale entries so the CLI can nudge the user to re-run
``mcp-aemps install`` — the canonical migration path.

Design constraints:

- **Read-only.** Never modifies any file. Re-running ``mcp-aemps
  install`` is the single source of truth for migrating; this module
  exists only to *surface* the need.
- **Conservative.** Only flags substrings that are unambiguously
  legacy (the v0.2 port lives on in nobody's intentional config).
  And only flags them when they appear inside the entry whose key
  matches ``SERVER_KEY`` — never against the file as a whole. False-
  positives from unrelated entries (e.g. a pre-rename ``aemps-cima``
  alias the user added manually) would degrade trust faster than
  false-negatives degrade utility.
- **Best-effort.** Permission errors, malformed configs, missing
  paths — all swallowed silently. We never crash the CLI just
  because we couldn't open a config.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from app.installers import (
    LEGACY_SERVER_KEYS,
    SERVER_KEY,
    antigravity_config_path,
    claude_code_config_path,
    claude_desktop_config_path,
    codex_config_path,
    continue_config_path,
    cursor_config_path,
    gemini_config_path,
    jetbrains_config_path,
    vscode_user_mcp_path,
    windsurf_config_path,
    zed_settings_path,
)

logger = logging.getLogger("mcp.aemps.migration_check")

# Config-file resolvers, keyed by the client name shown to users.
# Single source of truth — adding a new installer means adding the
# resolver here too.
_CONFIG_PATH_RESOLVERS: dict[str, Callable[[], Path]] = {
    "Claude Desktop": claude_desktop_config_path,
    "Claude Code": claude_code_config_path,
    "Codex CLI": codex_config_path,
    "Gemini CLI": gemini_config_path,
    "VS Code": vscode_user_mcp_path,
    "Cursor": cursor_config_path,
    "Windsurf": windsurf_config_path,
    "Zed": zed_settings_path,
    "Continue.dev": continue_config_path,
    "JetBrains Junie": jetbrains_config_path,
    "Antigravity": antigravity_config_path,
}

# Legacy substrings — currently only the pre-v0.2 default port. The
# current default port (8765) and stdio configs are NOT flagged
# because they may be intentional. Add new patterns here when a
# future default flip leaves stale substrings behind.
_LEGACY_SUBSTRINGS: tuple[str, ...] = (
    "localhost:8000",
    "127.0.0.1:8000",
    "[::1]:8000",
)


@dataclass(frozen=True)
class StaleConfig:
    """One client config file whose ``mcp-aemps`` entry contains a
    known-legacy substring. The CLI surfaces these as a nudge."""

    client: str
    path: Path
    legacy_pattern: str


def _extract_entry_text(path: Path, raw: str) -> Optional[str]:
    """Return the textual slice that covers *only* the ``mcp-aemps``
    entry within ``raw`` (the file's contents at ``path``). Returns
    ``None`` when the file doesn't have an entry under our key.

    Scoping the legacy-substring scan to the entry (not the file)
    rules out false positives from unrelated entries — e.g. a
    pre-rename ``aemps-cima`` alias under the same ``mcpServers``
    map that the user added before mcp-aemps adopted its current
    name. We only flag the entry we *manage*; legacy aliases are
    the user's to clean up manually."""
    suffix = path.suffix.lower()
    # JSON family — Claude Desktop, Claude Code, Cursor, Windsurf,
    # Zed, Continue.dev, JetBrains Junie, Antigravity, VS Code.
    if suffix in (".json", ".jsonc"):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        # Standard ``mcpServers`` map (most clients).
        block = data.get("mcpServers")
        if isinstance(block, dict) and SERVER_KEY in block:
            return json.dumps(block[SERVER_KEY])
        # ``mcpServers`` as a list (Continue.dev when stored as JSON
        # rather than YAML — defensive).
        if isinstance(block, list):
            for entry in block:
                if isinstance(entry, dict) and entry.get("name") == SERVER_KEY:
                    return json.dumps(entry)
        # VS Code's dedicated mcp.json uses ``servers``.
        block = data.get("servers")
        if isinstance(block, dict) and SERVER_KEY in block:
            return json.dumps(block[SERVER_KEY])
        # Zed's settings.json uses ``context_servers``.
        block = data.get("context_servers")
        if isinstance(block, dict) and SERVER_KEY in block:
            return json.dumps(block[SERVER_KEY])
        return None
    # TOML — Codex CLI. The block runs from the section header to
    # the next ``[`` or EOF.
    if suffix == ".toml":
        marker = f"[mcp_servers.{SERVER_KEY}]"
        idx = raw.find(marker)
        if idx == -1:
            return None
        rest = raw[idx + len(marker) :]
        next_section = rest.find("\n[")
        return rest if next_section == -1 else rest[:next_section]
    # YAML — Continue.dev. mcpServers is a list of entries; we look
    # for our ``name: mcp-aemps`` marker and grab a small window
    # around it.
    if suffix in (".yaml", ".yml"):
        marker = f"name: {SERVER_KEY}"
        idx = raw.find(marker)
        if idx == -1:
            return None
        return raw[idx : idx + 600]
    return None


def _has_legacy_alias(path: Path, raw: str) -> Optional[str]:
    """Return the first legacy server-key alias (e.g. ``aemps-cima``)
    found as a configured key inside ``raw``. The match is checked
    against per-format markers to avoid false positives from e.g.
    a comment that mentions the alias.

    Returns the alias name if present, ``None`` otherwise."""
    suffix = path.suffix.lower()
    if suffix in (".json", ".jsonc"):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        for parent_key in ("mcpServers", "servers", "context_servers"):
            block = data.get(parent_key)
            if isinstance(block, dict):
                for legacy_key in LEGACY_SERVER_KEYS:
                    if legacy_key in block:
                        return legacy_key
        return None
    if suffix == ".toml":
        for legacy_key in LEGACY_SERVER_KEYS:
            if f"[mcp_servers.{legacy_key}]" in raw:
                return legacy_key
        return None
    if suffix in (".yaml", ".yml"):
        for legacy_key in LEGACY_SERVER_KEYS:
            if f"name: {legacy_key}" in raw:
                return legacy_key
        return None
    return None


def find_stale_configs() -> list[StaleConfig]:
    """Scan all known client config files for either a legacy URL
    inside our ``mcp-aemps`` entry, or a legacy server-key alias
    (``aemps-cima``, etc.) anywhere in the relevant servers map.
    Returns at most one StaleConfig per client (the first matching
    signal wins) so the CLI nudge stays compact.

    Both signals are remediable by re-running ``mcp-aemps install``:
    legacy URLs get rewritten to the current desired entry; legacy
    aliases are purged from the same write (see
    ``app.installers._purge_legacy_aliases``)."""
    out: list[StaleConfig] = []
    for client, resolver in _CONFIG_PATH_RESOLVERS.items():
        try:
            path = resolver()
        except Exception:
            logger.debug("config path resolver for %s failed", client, exc_info=True)
            continue
        if not path.exists():
            continue
        try:
            raw = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            logger.debug("could not read %s", path, exc_info=True)
            continue
        # Signal 1: legacy URL inside our managed entry.
        entry = _extract_entry_text(path, raw)
        if entry is not None:
            url_hit = next((p for p in _LEGACY_SUBSTRINGS if p in entry), None)
            if url_hit is not None:
                out.append(StaleConfig(client=client, path=path, legacy_pattern=url_hit))
                continue
        # Signal 2: legacy server-key alias anywhere in the servers
        # map. Surfaced as a stale config so the CLI nudges the user
        # to run install (which purges aliases automatically).
        alias_hit = _has_legacy_alias(path, raw)
        if alias_hit is not None:
            out.append(StaleConfig(client=client, path=path, legacy_pattern=f"alias: {alias_hit}"))
    return out


__all__ = ["StaleConfig", "find_stale_configs"]
