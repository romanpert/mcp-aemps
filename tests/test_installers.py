"""Tests for the auto-install commands.

Always pass `config_path` to keep tests hermetic — never touches the user's
real Claude / Codex / VSCode / Cursor / Windsurf configs.
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
    install_jetbrains,
    install_vscode,
    install_windsurf,
    install_zed,
    uninstall_claude_code,
    uninstall_claude_desktop,
    uninstall_continue,
    uninstall_cursor,
    uninstall_jetbrains,
    uninstall_vscode,
    uninstall_windsurf,
    uninstall_zed,
)


# --- Claude Desktop -------------------------------------------------------
def test_claude_desktop_default_uses_uvx_stdio(tmp_path: Path) -> None:
    """Default transport is stdio — Claude Desktop launches `uvx mcp-aemps stdio`."""
    p = tmp_path / "claude_desktop_config.json"
    install_claude_desktop(config_path=p)
    data = json.loads(p.read_text(encoding="utf-8"))
    entry = data["mcpServers"]["mcp-aemps"]
    assert entry["command"] == "uvx"
    assert "mcp-aemps@latest" in entry["args"]
    assert "stdio" in entry["args"]
    # No HTTP url leaked into the entry
    assert "url" not in entry


def test_claude_desktop_http_mode_uses_mcp_remote_bridge(tmp_path: Path) -> None:
    """transport='http' falls back to npx mcp-remote bridge (for shared HTTP server)."""
    p = tmp_path / "claude_desktop_config.json"
    install_claude_desktop(url="http://localhost:9000/mcp", config_path=p, transport="http")
    data = json.loads(p.read_text(encoding="utf-8"))
    entry = data["mcpServers"]["mcp-aemps"]
    assert entry["command"] == "npx"
    assert "mcp-remote" in entry["args"]
    assert "http://localhost:9000/mcp" in entry["args"]


def test_claude_desktop_idempotent(tmp_path: Path) -> None:
    p = tmp_path / "claude_desktop_config.json"
    r1 = install_claude_desktop(config_path=p)
    assert r1.action == "added"
    r2 = install_claude_desktop(config_path=p)
    assert r2.action == "unchanged"
    # Switching to http mode must register as 'updated'
    r3 = install_claude_desktop(url="http://localhost:8080/mcp", config_path=p, transport="http")
    assert r3.action == "updated"


def test_claude_desktop_preserves_other_entries(tmp_path: Path) -> None:
    p = tmp_path / "claude_desktop_config.json"
    p.write_text(json.dumps({"mcpServers": {"existing-server": {"command": "foo"}}}))
    install_claude_desktop(url="http://localhost:9000/mcp", config_path=p)
    data = json.loads(p.read_text(encoding="utf-8"))
    assert "existing-server" in data["mcpServers"]
    assert "mcp-aemps" in data["mcpServers"]


def test_claude_desktop_uninstall_idempotent(tmp_path: Path) -> None:
    p = tmp_path / "claude_desktop_config.json"
    install_claude_desktop(url="http://localhost:9000/mcp", config_path=p)
    r1 = uninstall_claude_desktop(config_path=p)
    assert r1.action == "removed"
    r2 = uninstall_claude_desktop(config_path=p)
    assert r2.action == "unchanged"


# --- Claude Code ----------------------------------------------------------
def test_claude_code_fallback_path(tmp_path: Path) -> None:
    p = tmp_path / "claude.json"
    r = install_claude_code(url="http://localhost:9000/mcp", config_path=p, use_cli=False)
    assert r.action == "added"
    data = json.loads(p.read_text(encoding="utf-8"))
    entry = data["mcpServers"]["mcp-aemps"]
    assert entry["type"] == "http"
    assert entry["url"] == "http://localhost:9000/mcp"


def test_claude_code_preserves_other_entries(tmp_path: Path) -> None:
    p = tmp_path / "claude.json"
    p.write_text(json.dumps({"mcpServers": {"other": {"url": "x"}}}))
    install_claude_code(url="http://localhost:9000/mcp", config_path=p, use_cli=False)
    data = json.loads(p.read_text(encoding="utf-8"))
    assert "other" in data["mcpServers"]
    assert "mcp-aemps" in data["mcpServers"]


def test_claude_code_uninstall(tmp_path: Path) -> None:
    p = tmp_path / "claude.json"
    install_claude_code(url="http://localhost:9000/mcp", config_path=p, use_cli=False)
    r = uninstall_claude_code(config_path=p, use_cli=False)
    assert r.action == "removed"


# --- Codex ----------------------------------------------------------------
def test_codex_add_to_empty(tmp_path: Path) -> None:
    p = tmp_path / "config.toml"
    r = install_codex(url="http://localhost:9000/mcp", config_path=p)
    assert r.action == "added"
    text = p.read_text(encoding="utf-8")
    assert "[mcp_servers.mcp-aemps]" in text
    assert 'url = "http://localhost:9000/mcp"' in text


def test_codex_preserves_other_sections(tmp_path: Path) -> None:
    p = tmp_path / "config.toml"
    p.write_text('[other_section]\nfoo = "bar"\n')
    install_codex(url="http://localhost:9000/mcp", config_path=p)
    text = p.read_text(encoding="utf-8")
    assert "[other_section]" in text
    assert 'foo = "bar"' in text
    assert "[mcp_servers.mcp-aemps]" in text


def test_codex_idempotent_and_update(tmp_path: Path) -> None:
    p = tmp_path / "config.toml"
    install_codex(url="http://localhost:9000/mcp", config_path=p)
    r2 = install_codex(url="http://localhost:9000/mcp", config_path=p)
    assert r2.action == "unchanged"
    r3 = install_codex(url="http://localhost:8080/mcp", config_path=p)
    assert r3.action == "updated"
    assert 'url = "http://localhost:8080/mcp"' in p.read_text(encoding="utf-8")


# --- VS Code --------------------------------------------------------------
def test_vscode_writes_nested_mcp_servers(tmp_path: Path) -> None:
    p = tmp_path / "settings.json"
    r = install_vscode(url="http://localhost:9000/mcp", config_path=p)
    assert r.action == "added"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["mcp"]["servers"]["mcp-aemps"] == {
        "type": "http",
        "url": "http://localhost:9000/mcp",
    }


def test_vscode_preserves_other_settings(tmp_path: Path) -> None:
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"editor.fontSize": 14, "workbench.colorTheme": "Dark"}))
    install_vscode(url="http://localhost:9000/mcp", config_path=p)
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["editor.fontSize"] == 14
    assert data["workbench.colorTheme"] == "Dark"
    assert "mcp-aemps" in data["mcp"]["servers"]


def test_vscode_uninstall(tmp_path: Path) -> None:
    p = tmp_path / "settings.json"
    install_vscode(url="http://localhost:9000/mcp", config_path=p)
    r = uninstall_vscode(config_path=p)
    assert r.action == "removed"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert "mcp-aemps" not in data.get("mcp", {}).get("servers", {})


# --- Cursor ---------------------------------------------------------------
def test_cursor_add(tmp_path: Path) -> None:
    p = tmp_path / "mcp.json"
    r = install_cursor(url="http://localhost:9000/mcp", config_path=p)
    assert r.action == "added"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["mcpServers"]["mcp-aemps"] == {"url": "http://localhost:9000/mcp"}


def test_cursor_uninstall(tmp_path: Path) -> None:
    p = tmp_path / "mcp.json"
    install_cursor(url="http://localhost:9000/mcp", config_path=p)
    r = uninstall_cursor(config_path=p)
    assert r.action == "removed"


# --- Windsurf -------------------------------------------------------------
def test_windsurf_uses_serverUrl_field(tmp_path: Path) -> None:
    p = tmp_path / "mcp_config.json"
    r = install_windsurf(url="http://localhost:9000/mcp", config_path=p)
    assert r.action == "added"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["mcpServers"]["mcp-aemps"]["serverUrl"] == "http://localhost:9000/mcp"


def test_windsurf_uninstall(tmp_path: Path) -> None:
    p = tmp_path / "mcp_config.json"
    install_windsurf(url="http://localhost:9000/mcp", config_path=p)
    r = uninstall_windsurf(config_path=p)
    assert r.action == "removed"


# --- Zed ------------------------------------------------------------------
def test_zed_writes_context_servers(tmp_path: Path) -> None:
    p = tmp_path / "settings.json"
    r = install_zed(url="http://localhost:9000/mcp", config_path=p)
    assert r.action == "added"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["context_servers"]["mcp-aemps"] == {"url": "http://localhost:9000/mcp"}


def test_zed_preserves_other_settings(tmp_path: Path) -> None:
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"theme": "One Dark", "buffer_font_size": 14}))
    install_zed(url="http://localhost:9000/mcp", config_path=p)
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["theme"] == "One Dark"
    assert data["buffer_font_size"] == 14
    assert "mcp-aemps" in data["context_servers"]


def test_zed_idempotent_and_uninstall(tmp_path: Path) -> None:
    p = tmp_path / "settings.json"
    install_zed(url="http://localhost:9000/mcp", config_path=p)
    assert install_zed(url="http://localhost:9000/mcp", config_path=p).action == "unchanged"
    assert install_zed(url="http://localhost:8080/mcp", config_path=p).action == "updated"
    assert uninstall_zed(config_path=p).action == "removed"
    assert uninstall_zed(config_path=p).action == "unchanged"


# --- Continue.dev ---------------------------------------------------------
def test_continue_adds_block_to_empty_config(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    r = install_continue(url="http://localhost:9000/mcp", config_path=p)
    assert r.action == "added"
    text = p.read_text(encoding="utf-8")
    assert "mcp-aemps (managed by `mcp-aemps install continue`)" in text
    assert "name: mcp-aemps" in text
    assert "url: http://localhost:9000/mcp" in text


def test_continue_preserves_existing_yaml(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    p.write_text("models:\n  - name: gpt-4o\n    provider: openai\n", encoding="utf-8")
    install_continue(url="http://localhost:9000/mcp", config_path=p)
    text = p.read_text(encoding="utf-8")
    assert "models:" in text
    assert "name: gpt-4o" in text
    assert "name: mcp-aemps" in text


def test_continue_idempotent_and_update(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    install_continue(url="http://localhost:9000/mcp", config_path=p)
    assert install_continue(url="http://localhost:9000/mcp", config_path=p).action == "unchanged"
    r = install_continue(url="http://localhost:8080/mcp", config_path=p)
    assert r.action == "updated"
    assert "url: http://localhost:8080/mcp" in p.read_text(encoding="utf-8")
    assert "url: http://localhost:9000/mcp" not in p.read_text(encoding="utf-8")


def test_continue_uninstall_removes_only_managed_block(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    p.write_text("models:\n  - name: gpt-4o\n", encoding="utf-8")
    install_continue(url="http://localhost:9000/mcp", config_path=p)
    r = uninstall_continue(config_path=p)
    assert r.action == "removed"
    text = p.read_text(encoding="utf-8")
    assert "models:" in text
    assert "mcp-aemps" not in text
    assert uninstall_continue(config_path=p).action == "unchanged"


# --- JetBrains Junie ------------------------------------------------------
def test_jetbrains_writes_mcp_servers_block(tmp_path: Path) -> None:
    p = tmp_path / "mcp.json"
    r = install_jetbrains(url="http://localhost:9000/mcp", config_path=p)
    assert r.action == "added"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["mcpServers"]["mcp-aemps"] == {"type": "http", "url": "http://localhost:9000/mcp"}


def test_jetbrains_preserves_other_servers(tmp_path: Path) -> None:
    p = tmp_path / "mcp.json"
    p.write_text(json.dumps({"mcpServers": {"other": {"type": "stdio", "command": "x"}}}))
    install_jetbrains(url="http://localhost:9000/mcp", config_path=p)
    data = json.loads(p.read_text(encoding="utf-8"))
    assert "other" in data["mcpServers"]
    assert "mcp-aemps" in data["mcpServers"]


def test_jetbrains_idempotent_and_uninstall(tmp_path: Path) -> None:
    p = tmp_path / "mcp.json"
    install_jetbrains(url="http://localhost:9000/mcp", config_path=p)
    assert install_jetbrains(url="http://localhost:9000/mcp", config_path=p).action == "unchanged"
    assert install_jetbrains(url="http://localhost:8080/mcp", config_path=p).action == "updated"
    assert uninstall_jetbrains(config_path=p).action == "removed"
    assert uninstall_jetbrains(config_path=p).action == "unchanged"


# --- Registry symmetry ----------------------------------------------------
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
