"""Tests for the auto-install commands.

Always pass `config_path` to keep tests hermetic — never touches the user's
real Claude / Codex configs.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.installers import (
    install_claude_code,
    install_claude_desktop,
    install_codex,
    uninstall_claude_code,
    uninstall_claude_desktop,
)


# --- Claude Desktop -------------------------------------------------------
def test_claude_desktop_add_idempotent_update(tmp_path: Path) -> None:
    p = tmp_path / "claude_desktop_config.json"

    r1 = install_claude_desktop(url="http://localhost:9000/mcp", config_path=p)
    assert r1.action == "added"

    r2 = install_claude_desktop(url="http://localhost:9000/mcp", config_path=p)
    assert r2.action == "unchanged"

    r3 = install_claude_desktop(url="http://localhost:8080/mcp", config_path=p)
    assert r3.action == "updated"

    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["mcpServers"]["mcp-aemps"]["url"] == "http://localhost:8080/mcp"


def test_claude_desktop_preserves_other_entries(tmp_path: Path) -> None:
    p = tmp_path / "claude_desktop_config.json"
    p.write_text(json.dumps({"mcpServers": {"existing-server": {"command": "foo"}}}))

    install_claude_desktop(config_path=p)
    data = json.loads(p.read_text(encoding="utf-8"))
    assert "existing-server" in data["mcpServers"]
    assert "mcp-aemps" in data["mcpServers"]


def test_claude_desktop_uninstall_idempotent(tmp_path: Path) -> None:
    p = tmp_path / "claude_desktop_config.json"
    install_claude_desktop(config_path=p)

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
    install_codex(config_path=p)
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
    text = p.read_text(encoding="utf-8")
    assert 'url = "http://localhost:8080/mcp"' in text


# --- Path resolution per platform -----------------------------------------
def test_path_resolution_returns_path() -> None:
    from app.installers import (
        claude_code_config_path,
        claude_desktop_config_path,
        codex_config_path,
    )

    for fn in (claude_desktop_config_path, claude_code_config_path, codex_config_path):
        p = fn()
        assert isinstance(p, Path)
        assert p.is_absolute()
