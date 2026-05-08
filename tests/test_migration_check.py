"""Tests for app.migration_check — stale-config detector for the
``mcp-aemps install`` migration nudge."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import migration_check
from app.migration_check import (
    _LEGACY_SUBSTRINGS,
    StaleConfig,
    _extract_entry_text,
    find_stale_configs,
)


@pytest.fixture
def tmp_json(tmp_path: Path):
    def _make(name: str, data: dict) -> Path:
        p = tmp_path / name
        p.write_text(json.dumps(data), encoding="utf-8")
        return p

    return _make


# ---------------------------------------------------------------------------
# _extract_entry_text — per-format extraction
# ---------------------------------------------------------------------------


def test_extract_json_mcpservers_dict(tmp_json):
    path = tmp_json(
        "a.json", {"mcpServers": {"mcp-aemps": {"type": "http", "url": "http://localhost:8000/mcp"}}}
    )
    out = _extract_entry_text(path, path.read_text())
    assert out is not None
    assert "localhost:8000" in out


def test_extract_json_servers_dict_vscode(tmp_json):
    """VS Code uses ``servers`` instead of ``mcpServers``."""
    path = tmp_json("b.json", {"servers": {"mcp-aemps": {"type": "stdio", "command": "uvx"}}})
    out = _extract_entry_text(path, path.read_text())
    assert out is not None and "uvx" in out


def test_extract_json_context_servers_zed(tmp_json):
    """Zed's settings.json uses ``context_servers``."""
    path = tmp_json("c.json", {"context_servers": {"mcp-aemps": {"command": "uvx"}}})
    out = _extract_entry_text(path, path.read_text())
    assert out is not None and "uvx" in out


def test_extract_returns_none_when_key_missing(tmp_json):
    path = tmp_json("d.json", {"mcpServers": {"some-other": {"url": "http://x"}}})
    assert _extract_entry_text(path, path.read_text()) is None


def test_extract_returns_none_for_malformed_json(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{ not valid json", encoding="utf-8")
    assert _extract_entry_text(p, p.read_text()) is None


def test_extract_toml_codex(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(
        '[mcp_servers.other]\nurl = "x"\n\n'
        '[mcp_servers.mcp-aemps]\nurl = "http://localhost:8000/mcp"\n'
        "\n[mcp_servers.another]\n",
        encoding="utf-8",
    )
    out = _extract_entry_text(p, p.read_text())
    assert out is not None
    assert "localhost:8000" in out
    # Must not bleed into the next section
    assert "[mcp_servers.another]" not in out


def test_extract_yaml_continue(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(
        "mcpServers:\n"
        "  - name: other\n    command: x\n"
        "  - name: mcp-aemps\n"
        '    url: "http://localhost:8000/mcp"\n',
        encoding="utf-8",
    )
    out = _extract_entry_text(p, p.read_text())
    assert out is not None
    assert "localhost:8000" in out


def test_extract_unknown_suffix(tmp_path):
    p = tmp_path / "x.txt"
    p.write_text("mcp-aemps localhost:8000", encoding="utf-8")
    assert _extract_entry_text(p, p.read_text()) is None


# ---------------------------------------------------------------------------
# find_stale_configs — orchestration + filtering
# ---------------------------------------------------------------------------


def _patch_resolvers(monkeypatch, mapping):
    monkeypatch.setattr(migration_check, "_CONFIG_PATH_RESOLVERS", mapping)


def test_find_returns_stale_when_legacy_in_our_entry(tmp_json, monkeypatch):
    p = tmp_json(
        "claude.json",
        {"mcpServers": {"mcp-aemps": {"type": "http", "url": "http://localhost:8000/mcp"}}},
    )
    _patch_resolvers(monkeypatch, {"Claude Code": lambda: p})
    out = find_stale_configs()
    assert len(out) == 1
    assert isinstance(out[0], StaleConfig)
    assert out[0].client == "Claude Code"
    assert out[0].legacy_pattern in _LEGACY_SUBSTRINGS


def test_find_does_not_flag_legacy_url_outside_our_entry_when_no_alias(tmp_json, monkeypatch):
    """Legacy URL inside a NON-legacy unrelated key (e.g. user-named
    ``my-server``) must not flag — that's the user's tool, none of
    our business. Only legacy URLs in our entry, OR any of the
    KNOWN legacy aliases (covered by Signal 2 below), trigger a
    nudge."""
    p = tmp_json(
        "cursor.json",
        {
            "mcpServers": {
                "mcp-aemps": {"type": "stdio", "command": "uvx", "args": ["mcp-aemps@latest", "stdio"]},
                "my-server": {"url": "http://localhost:8000/mcp"},
            }
        },
    )
    _patch_resolvers(monkeypatch, {"Cursor": lambda: p})
    assert find_stale_configs() == []


def test_find_skips_missing_files(tmp_path, monkeypatch):
    _patch_resolvers(monkeypatch, {"Phantom": lambda: tmp_path / "nope.json"})
    assert find_stale_configs() == []


def test_find_skips_failing_resolver(monkeypatch):
    def _boom():
        raise RuntimeError("resolver failed")

    _patch_resolvers(monkeypatch, {"Broken": _boom})
    # Must not raise — best-effort contract.
    assert find_stale_configs() == []


def test_find_returns_at_most_one_per_client(tmp_json, monkeypatch):
    """Even with multiple legacy substrings in the same entry, we
    emit at most one StaleConfig per client to keep the CLI nudge
    compact."""
    p = tmp_json(
        "x.json",
        {"mcpServers": {"mcp-aemps": {"url": "http://localhost:8000/mcp http://127.0.0.1:8000/mcp"}}},
    )
    _patch_resolvers(monkeypatch, {"X": lambda: p})
    assert len(find_stale_configs()) == 1


def test_find_ignores_current_default_port(tmp_json, monkeypatch):
    """Current default port (8765) — whether stdio or http — is not
    legacy and must not be flagged."""
    p = tmp_json(
        "y.json",
        {"mcpServers": {"mcp-aemps": {"url": "http://localhost:8765/mcp"}}},
    )
    _patch_resolvers(monkeypatch, {"Y": lambda: p})
    assert find_stale_configs() == []


def test_find_handles_unreadable_file(tmp_path, monkeypatch):
    """Permission errors don't crash the scan."""
    p = tmp_path / "z.json"
    p.write_text("{}", encoding="utf-8")

    def _explode(*_a, **_kw):
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "read_text", _explode)
    _patch_resolvers(monkeypatch, {"Z": lambda: p})
    assert find_stale_configs() == []


# ---------------------------------------------------------------------------
# Legacy-alias detection (Signal 2)
# ---------------------------------------------------------------------------


def test_find_detects_legacy_alias_aemps_cima(tmp_json, monkeypatch):
    """A pre-rename ``aemps-cima`` key alongside the current
    ``mcp-aemps`` entry must be flagged so the CLI nudge tells the
    user to run install (which purges aliases automatically)."""
    p = tmp_json(
        "cursor.json",
        {
            "mcpServers": {
                "mcp-aemps": {"type": "stdio", "command": "uvx"},
                "aemps-cima": {"url": "http://example.com/anything"},
            }
        },
    )
    _patch_resolvers(monkeypatch, {"Cursor": lambda: p})
    out = find_stale_configs()
    assert len(out) == 1
    assert out[0].legacy_pattern == "alias: aemps-cima"


def test_find_detects_legacy_alias_in_vscode_servers_map(tmp_json, monkeypatch):
    """VS Code's dedicated mcp.json uses ``servers``, not ``mcpServers``."""
    p = tmp_json("vscode.json", {"servers": {"mcp-aemps-cima": {"command": "x"}}})
    _patch_resolvers(monkeypatch, {"VS Code": lambda: p})
    out = find_stale_configs()
    assert len(out) == 1 and out[0].legacy_pattern == "alias: mcp-aemps-cima"


def test_find_detects_legacy_alias_in_zed_context_servers(tmp_json, monkeypatch):
    p = tmp_json("zed.json", {"context_servers": {"aemps-cima": {"command": "x"}}})
    _patch_resolvers(monkeypatch, {"Zed": lambda: p})
    out = find_stale_configs()
    assert len(out) == 1 and out[0].legacy_pattern == "alias: aemps-cima"


def test_find_detects_legacy_alias_in_codex_toml(tmp_path, monkeypatch):
    p = tmp_path / "codex.toml"
    p.write_text(
        '[mcp_servers.mcp-aemps]\ncommand = "uvx"\n\n[mcp_servers.aemps-cima]\nurl = "http://x"\n',
        encoding="utf-8",
    )
    _patch_resolvers(monkeypatch, {"Codex CLI": lambda: p})
    out = find_stale_configs()
    assert len(out) == 1 and out[0].legacy_pattern == "alias: aemps-cima"


def test_find_url_signal_takes_priority_over_alias(tmp_json, monkeypatch):
    """If both signals hit, the URL signal wins (it's the more
    specific 'this entry needs to be rewritten' signal)."""
    p = tmp_json(
        "x.json",
        {
            "mcpServers": {
                "mcp-aemps": {"url": "http://localhost:8000/mcp"},
                "aemps-cima": {"url": "http://x"},
            }
        },
    )
    _patch_resolvers(monkeypatch, {"X": lambda: p})
    out = find_stale_configs()
    assert len(out) == 1
    assert out[0].legacy_pattern in _LEGACY_SUBSTRINGS  # URL signal, not "alias: ..."


def test_find_no_alias_no_url_no_flag(tmp_json, monkeypatch):
    """Clean config with the current canonical entry — must not flag."""
    p = tmp_json(
        "clean.json",
        {"mcpServers": {"mcp-aemps": {"type": "stdio", "command": "uvx"}}},
    )
    _patch_resolvers(monkeypatch, {"Clean": lambda: p})
    assert find_stale_configs() == []
