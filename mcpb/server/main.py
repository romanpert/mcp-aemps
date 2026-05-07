"""MCPB entry point — delegates to the canonical stdio server.

The MCPB host (Claude for Mac/Windows) starts this script via the bundled
``uv`` runtime. ``uv`` reads the sibling ``pyproject.toml`` to install
``mcp-aemps`` from PyPI on first run, then re-uses the cached venv for
every subsequent launch — so the bundle itself stays small (no vendored
dependencies) while installation is single-click.

Environment variables exposed by the manifest's ``user_config`` block
(``LOG_LEVEL``, ``REDIS_URL``, ``MCP_AEMPS_LOCALE``) are applied via the
host before this file runs; we don't need to touch them here.
"""

from __future__ import annotations


def main() -> None:
    # Imported lazily so a top-level import error surfaces with the same
    # traceback the MCPB host expects rather than at module load time.
    from app.stdio_server import main as _stdio_main

    _stdio_main()


if __name__ == "__main__":
    main()
