"""Tests for the auto-install commands.

Always pass ``config_path`` to keep tests hermetic — never touches the
user's real Claude / Codex / VS Code / Cursor / Windsurf configs.

**Schema invariants pinned 2026-05-08** after the v0.4.10 audit pass.
Every installer defaults to **stdio** with the canonical
``{"command": "uvx", "args": ["mcp-aemps@latest", "stdio"]}`` block.
HTTP is opt-in via ``transport="http"`` for shared deployments. The
test set covers both paths so a regression to "URL by default" or to
the deprecated VS Code ``settings.json::mcp.servers`` location fails
loudly at CI time.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.installers import (
    install_claude_code,
    install_claude_desktop,
    install_codex,
    install_continue,
    install_cursor,
    install_gemini,
    install_jetbrains,
    install_vscode,
    install_windsurf,
    install_zed,
    uninstall_claude_code,
    uninstall_claude_desktop,
    uninstall_continue,
    uninstall_cursor,
    uninstall_gemini,
    uninstall_jetbrains,
    uninstall_vscode,
    uninstall_windsurf,
    uninstall_zed,
)

UVX_LAUNCHER_ARGS = ["mcp-aemps@latest", "stdio"]


def _assert_stdio(entry: dict) -> None:
    """Shared invariant: every stdio-default installer must produce
    the canonical uvx-based block — no localhost URL, no port, no
    HTTP-bridge command."""
    assert entry.get("command") == "uvx", entry
    assert entry.get("args") == UVX_LAUNCHER_ARGS, entry
    assert "url" not in entry, entry
    assert "serverUrl" not in entry, entry


# --- Claude Desktop -------------------------------------------------------
def test_claude_desktop_default_uses_uvx_stdio(tmp_path: Path) -> None:
    p = tmp_path / "claude_desktop_config.json"
    install_claude_desktop(config_path=p)
    data = json.loads(p.read_text(encoding="utf-8"))
    _assert_stdio(data["mcpServers"]["mcp-aemps"])


def test_claude_desktop_http_mode_uses_mcp_remote_bridge(tmp_path: Path) -> None:
    p = tmp_path / "claude_desktop_config.json"
    install_claude_desktop(url="http://localhost:9000/mcp", config_path=p, transport="http")
    entry = json.loads(p.read_text(encoding="utf-8"))["mcpServers"]["mcp-aemps"]
    assert entry["command"] == "npx"
    assert "mcp-remote" in entry["args"]
    assert "http://localhost:9000/mcp" in entry["args"]


def test_claude_desktop_idempotent(tmp_path: Path) -> None:
    p = tmp_path / "claude_desktop_config.json"
    install_claude_desktop(config_path=p)
    r2 = install_claude_desktop(config_path=p)
    assert r2.action == "unchanged"


def test_claude_desktop_preserves_other_entries(tmp_path: Path) -> None:
    p = tmp_path / "claude_desktop_config.json"
    p.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}}))
    install_claude_desktop(config_path=p)
    data = json.loads(p.read_text(encoding="utf-8"))
    assert "other" in data["mcpServers"]
    assert "mcp-aemps" in data["mcpServers"]


def test_claude_desktop_uninstall_idempotent(tmp_path: Path) -> None:
    p = tmp_path / "claude_desktop_config.json"
    install_claude_desktop(config_path=p)
    assert uninstall_claude_desktop(config_path=p).action == "removed"
    assert uninstall_claude_desktop(config_path=p).action == "unchanged"


# --- Claude Code ----------------------------------------------------------
def test_claude_code_default_writes_stdio_to_fallback_path(tmp_path: Path) -> None:
    p = tmp_path / "claude.json"
    r = install_claude_code(config_path=p, use_cli=False)
    assert r.action == "added"
    _assert_stdio(json.loads(p.read_text(encoding="utf-8"))["mcpServers"]["mcp-aemps"])


def test_claude_code_http_mode_writes_url(tmp_path: Path) -> None:
    p = tmp_path / "claude.json"
    install_claude_code(
        url="http://shared.example.com:9000/mcp",
        config_path=p,
        use_cli=False,
        transport="http",
    )
    entry = json.loads(p.read_text(encoding="utf-8"))["mcpServers"]["mcp-aemps"]
    assert entry == {"type": "http", "url": "http://shared.example.com:9000/mcp"}


def test_claude_code_preserves_other_entries(tmp_path: Path) -> None:
    p = tmp_path / "claude.json"
    p.write_text(json.dumps({"mcpServers": {"other": {"url": "x"}}}))
    install_claude_code(config_path=p, use_cli=False)
    data = json.loads(p.read_text(encoding="utf-8"))
    assert "other" in data["mcpServers"]
    assert "mcp-aemps" in data["mcpServers"]


def test_claude_code_uninstall(tmp_path: Path) -> None:
    p = tmp_path / "claude.json"
    install_claude_code(config_path=p, use_cli=False)
    r = uninstall_claude_code(config_path=p, use_cli=False)
    assert r.action == "removed"


# --- Codex ----------------------------------------------------------------
def test_codex_default_writes_stdio_block(tmp_path: Path) -> None:
    p = tmp_path / "config.toml"
    r = install_codex(config_path=p)
    assert r.action == "added"
    text = p.read_text(encoding="utf-8")
    assert "[mcp_servers.mcp-aemps]" in text
    assert 'command = "uvx"' in text
    assert '"mcp-aemps@latest"' in text and '"stdio"' in text
    assert "url =" not in text  # no leaked HTTP fallback


def test_codex_http_mode_writes_url(tmp_path: Path) -> None:
    p = tmp_path / "config.toml"
    install_codex(url="http://shared.example.com:9000/mcp", config_path=p, transport="http")
    text = p.read_text(encoding="utf-8")
    assert 'url = "http://shared.example.com:9000/mcp"' in text
    assert 'transport = "http"' in text


def test_codex_preserves_other_sections(tmp_path: Path) -> None:
    p = tmp_path / "config.toml"
    p.write_text('[other_section]\nfoo = "bar"\n')
    install_codex(config_path=p)
    text = p.read_text(encoding="utf-8")
    assert "[other_section]" in text and 'foo = "bar"' in text
    assert "[mcp_servers.mcp-aemps]" in text


def test_codex_idempotent_and_update(tmp_path: Path) -> None:
    p = tmp_path / "config.toml"
    install_codex(config_path=p)
    assert install_codex(config_path=p).action == "unchanged"
    r3 = install_codex(config_path=p, transport="http", url="http://localhost:8080/mcp")
    assert r3.action == "updated"


# --- VS Code (dedicated mcp.json — NOT the deprecated settings.json) -----
def test_vscode_default_writes_stdio_to_dedicated_mcp_json(tmp_path: Path) -> None:
    """The post-2025 VS Code MCP location is ``mcp.json::servers``, not
    the deprecated ``settings.json::mcp.servers``. A regression here
    would resurrect VS Code's deprecation banner on every install."""
    p = tmp_path / "mcp.json"
    r = install_vscode(config_path=p)
    assert r.action == "added"
    data = json.loads(p.read_text(encoding="utf-8"))
    # Top-level ``servers`` key, NOT nested under ``mcp``.
    assert "servers" in data and "mcp" not in data
    _assert_stdio(data["servers"]["mcp-aemps"])


def test_vscode_http_mode_writes_type_http(tmp_path: Path) -> None:
    p = tmp_path / "mcp.json"
    install_vscode(url="http://shared.example.com:9000/mcp", config_path=p, transport="http")
    entry = json.loads(p.read_text(encoding="utf-8"))["servers"]["mcp-aemps"]
    assert entry == {"type": "http", "url": "http://shared.example.com:9000/mcp"}


def test_vscode_preserves_other_settings(tmp_path: Path) -> None:
    p = tmp_path / "mcp.json"
    p.write_text(json.dumps({"inputs": [{"id": "foo"}]}))
    install_vscode(config_path=p)
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["inputs"] == [{"id": "foo"}]
    assert "mcp-aemps" in data["servers"]


def test_vscode_uninstall(tmp_path: Path) -> None:
    p = tmp_path / "mcp.json"
    install_vscode(config_path=p)
    assert uninstall_vscode(config_path=p).action == "removed"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert "mcp-aemps" not in data.get("servers", {})


# --- Cursor ---------------------------------------------------------------
def test_cursor_default_writes_stdio(tmp_path: Path) -> None:
    p = tmp_path / "mcp.json"
    install_cursor(config_path=p)
    data = json.loads(p.read_text(encoding="utf-8"))
    _assert_stdio(data["mcpServers"]["mcp-aemps"])


def test_cursor_http_mode_writes_url(tmp_path: Path) -> None:
    p = tmp_path / "mcp.json"
    install_cursor(url="http://shared.example.com:9000/mcp", config_path=p, transport="http")
    entry = json.loads(p.read_text(encoding="utf-8"))["mcpServers"]["mcp-aemps"]
    assert entry == {"url": "http://shared.example.com:9000/mcp"}


def test_cursor_uninstall(tmp_path: Path) -> None:
    p = tmp_path / "mcp.json"
    install_cursor(config_path=p)
    assert uninstall_cursor(config_path=p).action == "removed"


# --- Windsurf -------------------------------------------------------------
def test_windsurf_default_writes_stdio(tmp_path: Path) -> None:
    p = tmp_path / "mcp_config.json"
    install_windsurf(config_path=p)
    data = json.loads(p.read_text(encoding="utf-8"))
    _assert_stdio(data["mcpServers"]["mcp-aemps"])


def test_windsurf_http_mode_uses_serverUrl_field(tmp_path: Path) -> None:
    """Windsurf is the only client that uses ``serverUrl`` (not ``url``)
    for HTTP entries — the field-name distinction matters."""
    p = tmp_path / "mcp_config.json"
    install_windsurf(url="http://shared.example.com:9000/mcp", config_path=p, transport="http")
    entry = json.loads(p.read_text(encoding="utf-8"))["mcpServers"]["mcp-aemps"]
    assert entry == {"serverUrl": "http://shared.example.com:9000/mcp"}


def test_windsurf_uninstall(tmp_path: Path) -> None:
    p = tmp_path / "mcp_config.json"
    install_windsurf(config_path=p)
    assert uninstall_windsurf(config_path=p).action == "removed"


# --- Zed ------------------------------------------------------------------
def test_zed_default_writes_stdio_with_empty_env(tmp_path: Path) -> None:
    """Zed's schema requires the ``env`` key on context_servers entries
    even when empty — the empty object MUST be present."""
    p = tmp_path / "settings.json"
    install_zed(config_path=p)
    entry = json.loads(p.read_text(encoding="utf-8"))["context_servers"]["mcp-aemps"]
    assert entry == {
        "command": "uvx",
        "args": UVX_LAUNCHER_ARGS,
        "env": {},
    }


def test_zed_http_mode_writes_url(tmp_path: Path) -> None:
    p = tmp_path / "settings.json"
    install_zed(url="http://shared.example.com:9000/mcp", config_path=p, transport="http")
    entry = json.loads(p.read_text(encoding="utf-8"))["context_servers"]["mcp-aemps"]
    assert entry == {"url": "http://shared.example.com:9000/mcp"}


def test_zed_preserves_other_settings(tmp_path: Path) -> None:
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"theme": "One Dark", "buffer_font_size": 14}))
    install_zed(config_path=p)
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["theme"] == "One Dark"
    assert data["buffer_font_size"] == 14
    assert "mcp-aemps" in data["context_servers"]


def test_zed_idempotent_and_uninstall(tmp_path: Path) -> None:
    p = tmp_path / "settings.json"
    install_zed(config_path=p)
    assert install_zed(config_path=p).action == "unchanged"
    assert install_zed(config_path=p, transport="http", url="http://x:1/mcp").action == "updated"
    assert uninstall_zed(config_path=p).action == "removed"
    assert uninstall_zed(config_path=p).action == "unchanged"


# --- Continue.dev ---------------------------------------------------------
def test_continue_default_writes_stdio_block(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    r = install_continue(config_path=p)
    assert r.action == "added"
    text = p.read_text(encoding="utf-8")
    assert "mcp-aemps (managed by `mcp-aemps install continue`)" in text
    assert "name: mcp-aemps" in text
    assert "type: stdio" in text
    assert "command: uvx" in text


def test_continue_http_mode_uses_streamable_http_type(tmp_path: Path) -> None:
    """``type: http`` is invalid in Continue's schema (silently no-ops);
    HTTP entries must use ``streamable-http`` or ``sse``."""
    p = tmp_path / "config.yaml"
    install_continue(url="http://shared.example.com:9000/mcp", config_path=p, transport="http")
    text = p.read_text(encoding="utf-8")
    assert "type: streamable-http" in text
    assert "type: http" not in text  # invalid value must NOT be written
    assert "url: http://shared.example.com:9000/mcp" in text


def test_continue_preserves_existing_yaml(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    p.write_text("models:\n  - name: gpt-4o\n    provider: openai\n", encoding="utf-8")
    install_continue(config_path=p)
    text = p.read_text(encoding="utf-8")
    assert "models:" in text and "name: gpt-4o" in text
    assert "name: mcp-aemps" in text


def test_continue_idempotent_and_update(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    install_continue(config_path=p)
    assert install_continue(config_path=p).action == "unchanged"
    r = install_continue(config_path=p, transport="http", url="http://shared:8080/mcp")
    assert r.action == "updated"
    assert "url: http://shared:8080/mcp" in p.read_text(encoding="utf-8")


def test_continue_uninstall_removes_only_managed_block(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    p.write_text("models:\n  - name: gpt-4o\n", encoding="utf-8")
    install_continue(config_path=p)
    assert uninstall_continue(config_path=p).action == "removed"
    text = p.read_text(encoding="utf-8")
    assert "models:" in text and "mcp-aemps" not in text
    assert uninstall_continue(config_path=p).action == "unchanged"


# --- JetBrains Junie ------------------------------------------------------
def test_jetbrains_default_writes_stdio(tmp_path: Path) -> None:
    p = tmp_path / "mcp.json"
    install_jetbrains(config_path=p)
    data = json.loads(p.read_text(encoding="utf-8"))
    _assert_stdio(data["mcpServers"]["mcp-aemps"])


def test_jetbrains_http_mode_writes_type_http(tmp_path: Path) -> None:
    p = tmp_path / "mcp.json"
    install_jetbrains(url="http://shared.example.com:9000/mcp", config_path=p, transport="http")
    entry = json.loads(p.read_text(encoding="utf-8"))["mcpServers"]["mcp-aemps"]
    assert entry == {"type": "http", "url": "http://shared.example.com:9000/mcp"}


def test_jetbrains_preserves_other_servers(tmp_path: Path) -> None:
    p = tmp_path / "mcp.json"
    p.write_text(json.dumps({"mcpServers": {"other": {"type": "stdio", "command": "x"}}}))
    install_jetbrains(config_path=p)
    data = json.loads(p.read_text(encoding="utf-8"))
    assert "other" in data["mcpServers"] and "mcp-aemps" in data["mcpServers"]


def test_jetbrains_idempotent_and_uninstall(tmp_path: Path) -> None:
    p = tmp_path / "mcp.json"
    install_jetbrains(config_path=p)
    assert install_jetbrains(config_path=p).action == "unchanged"
    assert (
        install_jetbrains(config_path=p, transport="http", url="http://shared:8080/mcp").action == "updated"
    )
    assert uninstall_jetbrains(config_path=p).action == "removed"
    assert uninstall_jetbrains(config_path=p).action == "unchanged"


# --- Cross-installer invariants ------------------------------------------
def test_no_default_install_writes_localhost_anywhere(tmp_path: Path) -> None:
    """Regression guard for the v0.4.x bug where 7/9 installers defaulted
    to ``http://localhost:8765/mcp`` — silently broken unless the user
    happened to have ``mcp-aemps up`` running. After v0.4.10 every
    default-install must be stdio (no localhost in the written config)."""
    paths = {
        "claude_desktop": tmp_path / "claude_desktop_config.json",
        "claude_code": tmp_path / "claude.json",
        "codex": tmp_path / "config.toml",
        "vscode": tmp_path / "vscode-mcp.json",
        "cursor": tmp_path / "cursor-mcp.json",
        "windsurf": tmp_path / "windsurf-mcp.json",
        "zed": tmp_path / "zed-settings.json",
        "continue": tmp_path / "continue-config.yaml",
        "jetbrains": tmp_path / "jetbrains-mcp.json",
    }
    install_claude_desktop(config_path=paths["claude_desktop"])
    install_claude_code(config_path=paths["claude_code"], use_cli=False)
    install_codex(config_path=paths["codex"])
    install_vscode(config_path=paths["vscode"])
    install_cursor(config_path=paths["cursor"])
    install_windsurf(config_path=paths["windsurf"])
    install_zed(config_path=paths["zed"])
    install_continue(config_path=paths["continue"])
    install_jetbrains(config_path=paths["jetbrains"])

    for name, p in paths.items():
        text = p.read_text(encoding="utf-8")
        assert "localhost" not in text, f"{name} install leaked localhost into {p}: {text[:200]}"


def test_all_installers_have_matching_uninstaller() -> None:
    from app.installers import ALL_INSTALLERS, ALL_UNINSTALLERS

    assert set(ALL_INSTALLERS.keys()) == set(ALL_UNINSTALLERS.keys()), (
        "Every installer must have a matching uninstaller (and vice-versa). "
        f"only-install: {set(ALL_INSTALLERS) - set(ALL_UNINSTALLERS)}; "
        f"only-uninstall: {set(ALL_UNINSTALLERS) - set(ALL_INSTALLERS)}"
    )


# --- Path resolution per platform -----------------------------------------
def test_path_resolution_returns_absolute_path() -> None:
    from app.installers import (
        claude_code_config_path,
        claude_desktop_config_path,
        codex_config_path,
        continue_config_path,
        cursor_config_path,
        jetbrains_config_path,
        vscode_settings_path,
        windsurf_config_path,
        zed_settings_path,
    )

    for fn in (
        claude_desktop_config_path,
        claude_code_config_path,
        codex_config_path,
        cursor_config_path,
        vscode_settings_path,
        windsurf_config_path,
        zed_settings_path,
        continue_config_path,
        jetbrains_config_path,
    ):
        p = fn()
        assert isinstance(p, Path)
        assert p.is_absolute()


def test_vscode_settings_path_now_points_at_dedicated_mcp_json() -> None:
    """v0.4.10 migration: ``vscode_settings_path`` is aliased to the new
    ``mcp.json`` location. Tests / docs that imported the old name keep
    working but point at the new file."""
    from app.installers import vscode_settings_path, vscode_user_mcp_path

    assert vscode_settings_path() == vscode_user_mcp_path()


# ---------------------------------------------------------------------------
# Legacy-alias purge — every JSON installer drops historical server keys
# (e.g. ``aemps-cima``, ``mcp-aemps-cima``) on install. v0.4.16+.
# ---------------------------------------------------------------------------


def _seed_with_legacy(path: Path, parent_key: str, alias: str = "aemps-cima") -> None:
    """Write a config file that contains both an unrelated entry and a
    legacy-alias entry under the given parent (``mcpServers`` /
    ``servers`` / ``context_servers``). The unrelated entry must
    survive the install; the alias must be purged."""
    path.write_text(
        json.dumps(
            {
                parent_key: {
                    "weather": {"command": "python", "args": ["weather.py"]},
                    alias: {"url": "http://localhost:8000/mcp"},
                }
            }
        ),
        encoding="utf-8",
    )


def _assert_purged_alias_preserves_unrelated(data: dict, parent_key: str) -> None:
    block = data[parent_key]
    assert "weather" in block, "unrelated entry was lost"
    assert "aemps-cima" not in block, "legacy alias was not purged"
    assert "mcp-aemps" in block, "current entry was not written"


def test_claude_desktop_purges_legacy_alias(tmp_path: Path) -> None:
    p = tmp_path / "cd.json"
    _seed_with_legacy(p, "mcpServers")
    res = install_claude_desktop(config_path=p)
    assert res.action == "updated"
    _assert_purged_alias_preserves_unrelated(json.loads(p.read_text(encoding="utf-8")), "mcpServers")


def test_claude_code_purges_legacy_alias(tmp_path: Path) -> None:
    p = tmp_path / "cc.json"
    _seed_with_legacy(p, "mcpServers")
    res = install_claude_code(config_path=p)
    assert res.action == "updated"
    _assert_purged_alias_preserves_unrelated(json.loads(p.read_text(encoding="utf-8")), "mcpServers")


def test_cursor_purges_legacy_alias(tmp_path: Path) -> None:
    p = tmp_path / "cur.json"
    _seed_with_legacy(p, "mcpServers")
    res = install_cursor(config_path=p)
    assert res.action == "updated"
    _assert_purged_alias_preserves_unrelated(json.loads(p.read_text(encoding="utf-8")), "mcpServers")


def test_windsurf_purges_legacy_alias(tmp_path: Path) -> None:
    p = tmp_path / "ws.json"
    _seed_with_legacy(p, "mcpServers")
    res = install_windsurf(config_path=p)
    assert res.action == "updated"
    _assert_purged_alias_preserves_unrelated(json.loads(p.read_text(encoding="utf-8")), "mcpServers")


def test_jetbrains_purges_legacy_alias(tmp_path: Path) -> None:
    p = tmp_path / "jb.json"
    _seed_with_legacy(p, "mcpServers")
    res = install_jetbrains(config_path=p)
    assert res.action == "updated"
    _assert_purged_alias_preserves_unrelated(json.loads(p.read_text(encoding="utf-8")), "mcpServers")


def test_vscode_purges_legacy_alias(tmp_path: Path) -> None:
    p = tmp_path / "vs.json"
    _seed_with_legacy(p, "servers")
    res = install_vscode(config_path=p)
    assert res.action == "updated"
    _assert_purged_alias_preserves_unrelated(json.loads(p.read_text(encoding="utf-8")), "servers")


def test_zed_purges_legacy_alias(tmp_path: Path) -> None:
    p = tmp_path / "zed.json"
    p.write_text(
        json.dumps(
            {
                "context_servers": {
                    "weather": {"command": "python", "args": ["weather.py"]},
                    "aemps-cima": {"url": "http://localhost:8000/mcp"},
                }
            }
        ),
        encoding="utf-8",
    )
    res = install_zed(config_path=p)
    assert res.action == "updated"
    _assert_purged_alias_preserves_unrelated(json.loads(p.read_text(encoding="utf-8")), "context_servers")


def test_codex_purges_legacy_toml_block(tmp_path: Path) -> None:
    p = tmp_path / "config.toml"
    p.write_text(
        '[mcp_servers.weather]\ncommand = "python"\n\n'
        '[mcp_servers.aemps-cima]\nurl = "http://localhost:8000/mcp"\n\n'
        '[mcp_servers.unrelated]\nfoo = "bar"\n',
        encoding="utf-8",
    )
    res = install_codex(config_path=p)
    assert res.action in ("added", "updated")
    text = p.read_text(encoding="utf-8")
    assert "[mcp_servers.aemps-cima]" not in text
    assert "[mcp_servers.weather]" in text
    assert "[mcp_servers.unrelated]" in text
    assert "[mcp_servers.mcp-aemps]" in text


def test_purge_idempotent_on_clean_config(tmp_path: Path) -> None:
    """Running install twice on a clean config must not re-introduce
    'updated' on the second run — purge only fires when something
    was actually present."""
    p = tmp_path / "clean.json"
    install_cursor(config_path=p)
    second = install_cursor(config_path=p)
    assert second.action == "unchanged", second


# ---------------------------------------------------------------------------
# Gemini CLI (Google's @google/gemini-cli, MCP-native, v0.4.17+)
# ---------------------------------------------------------------------------


def test_gemini_default_writes_stdio_no_type_field(tmp_path: Path) -> None:
    """Gemini CLI's stdio shape: command + args, NO ``type``
    discriminator (transport is inferred from which key is present)."""
    p = tmp_path / "settings.json"
    r = install_gemini(config_path=p)
    assert r.action == "added"
    entry = json.loads(p.read_text(encoding="utf-8"))["mcpServers"]["mcp-aemps"]
    assert entry == {"command": "uvx", "args": UVX_LAUNCHER_ARGS}
    assert "type" not in entry, "Gemini CLI does not use a type field"


def test_gemini_http_mode_uses_httpurl_field(tmp_path: Path) -> None:
    """Gemini CLI uses ``httpUrl`` for Streamable HTTP — NOT ``url``
    (which is SSE) and NOT ``serverUrl`` (Windsurf / Antigravity).
    Wrong field silently disables the server."""
    p = tmp_path / "settings.json"
    install_gemini(url="http://shared.example.com:9000/mcp", config_path=p, transport="http")
    entry = json.loads(p.read_text(encoding="utf-8"))["mcpServers"]["mcp-aemps"]
    assert entry == {"httpUrl": "http://shared.example.com:9000/mcp"}
    assert "url" not in entry
    assert "serverUrl" not in entry


def test_gemini_idempotent(tmp_path: Path) -> None:
    p = tmp_path / "settings.json"
    install_gemini(config_path=p)
    assert install_gemini(config_path=p).action == "unchanged"


def test_gemini_preserves_other_entries(tmp_path: Path) -> None:
    p = tmp_path / "settings.json"
    p.write_text(
        json.dumps(
            {
                "theme": "dark",
                "mcpServers": {"weather": {"command": "python", "args": ["w.py"]}},
            }
        ),
        encoding="utf-8",
    )
    install_gemini(config_path=p)
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["theme"] == "dark", "non-mcp keys must be preserved"
    assert "weather" in data["mcpServers"]
    assert "mcp-aemps" in data["mcpServers"]


def test_gemini_purges_legacy_alias(tmp_path: Path) -> None:
    p = tmp_path / "settings.json"
    p.write_text(
        json.dumps({"mcpServers": {"aemps-cima": {"httpUrl": "http://localhost:8000/mcp"}}}),
        encoding="utf-8",
    )
    res = install_gemini(config_path=p)
    assert res.action in ("added", "updated")
    data = json.loads(p.read_text(encoding="utf-8"))
    assert "aemps-cima" not in data["mcpServers"]
    assert "mcp-aemps" in data["mcpServers"]


def test_gemini_uninstall(tmp_path: Path) -> None:
    p = tmp_path / "settings.json"
    install_gemini(config_path=p)
    r = uninstall_gemini(config_path=p)
    assert r.action == "removed"
    assert uninstall_gemini(config_path=p).action == "unchanged"


def test_gemini_in_all_installers_registry() -> None:
    from app.installers import ALL_INSTALLERS, ALL_UNINSTALLERS

    assert "gemini" in ALL_INSTALLERS
    assert "gemini" in ALL_UNINSTALLERS


# ---------------------------------------------------------------------------
# v0.5.0 — strict detection (no host-IDE false positives)
# ---------------------------------------------------------------------------


def test_continue_detection_globs_extension_dir(monkeypatch, tmp_path: Path) -> None:
    """Continue.dev detection requires the actual extension dir
    (versioned, prefix `continue.continue-`), NOT just a host
    IDE's extensions/ folder. The latter would false-positive
    whenever VS Code is installed."""
    from app import installers

    monkeypatch.setattr(installers.Path, "home", lambda: tmp_path)

    # Set up a fake VS Code with NO Continue extension — must be
    # NOT detected.
    vscode_extensions = tmp_path / ".vscode" / "extensions"
    vscode_extensions.mkdir(parents=True)
    (vscode_extensions / "ms-python.python-2024.0.0").mkdir()
    assert not installers._app_glob_present("Continue.dev"), (
        "host IDE without Continue extension must NOT be detected"
    )

    # Add the Continue extension dir — now detection must hit.
    (vscode_extensions / "continue.continue-1.2.3").mkdir()
    assert installers._app_glob_present("Continue.dev"), "Continue extension dir present must be detected"


def test_junie_detection_requires_junie_only_files(monkeypatch, tmp_path: Path) -> None:
    """JetBrains Junie detection requires Junie-specific files
    (`AGENTS.md`, `.aiignore`), NOT just the JetBrains config
    root. Otherwise any user with PyCharm or IntelliJ would be
    falsely detected as having Junie."""
    from app import installers

    monkeypatch.setattr(installers.Path, "home", lambda: tmp_path)

    # An empty ~/.junie/ (which mcp-aemps could have created
    # writing mcp.json) must NOT count as Junie installed.
    (tmp_path / ".junie").mkdir()
    paths = installers._app_executables("JetBrains Junie")
    assert not any(p.exists() for p in paths), "empty ~/.junie/ must not satisfy detection"

    # Once Junie itself drops AGENTS.md, detection hits.
    (tmp_path / ".junie" / "AGENTS.md").write_text("# project guidance", encoding="utf-8")
    paths = installers._app_executables("JetBrains Junie")
    assert any(p.exists() for p in paths), "AGENTS.md must satisfy detection"


def test_claude_desktop_linux_returns_empty(monkeypatch) -> None:
    """Anthropic does not ship Claude Desktop on Linux. Pre-v0.5
    we made up `/snap/claude-desktop` paths — that's gone."""
    from app import installers

    monkeypatch.setattr(installers.sys, "platform", "linux")
    paths = installers._app_executables("Claude Desktop")
    assert paths == (), f"Claude Desktop on Linux must return empty paths, got {paths}"


def test_gemini_telltale_paths_removed(monkeypatch) -> None:
    """Pre-v0.5 we guessed `~/.gemini/oauth_creds.json` and
    `~/.gemini/google_account_id` as detection signals. Official
    Gemini CLI docs don't publish stable filenames, so those
    guesses are gone — detection now relies on `gemini` on PATH
    only (false-negatives acceptable, false-positives are not)."""
    from app import installers

    paths = installers._app_executables("Gemini CLI")
    assert paths == (), f"Gemini CLI must rely on PATH only, got {paths}"


def test_readme_carries_mcp_name_marker() -> None:
    """The MCP Registry publish endpoint validates that the package
    README contains `mcp-name: <server-name>` literal. v0.4.17
    release failed with HTTP 400 because the marker was missing.
    Both READMEs ship the marker; both must keep it for every
    future release."""
    repo_root = Path(__file__).parent.parent
    expected = "mcp-name: io.github.romanpert/mcp-aemps"
    for readme in (repo_root / "README.md", repo_root / "README.en.md"):
        text = readme.read_text(encoding="utf-8")
        assert expected in text, f"{readme.name} missing MCP Registry marker `{expected}`"
