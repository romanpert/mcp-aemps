# mcp-aemps (npm wrapper)

Thin Node.js wrapper around the [`mcp-aemps` Python package](https://pypi.org/project/mcp-aemps/).
Lets MCP clients launch the server with `npx mcp-aemps@latest` instead of
needing Python tooling explicitly.

## Usage

In your MCP client's config (Claude Desktop, Cursor, Windsurf, …):

```json
{
  "mcpServers": {
    "mcp-aemps": {
      "command": "npx",
      "args": ["-y", "mcp-aemps@latest"]
    }
  }
}
```

That's it — no port, no URL, no Python install step. The wrapper finds
`uv` (`uvx`), `pipx`, or a pip-installed `mcp-aemps` automatically.

## How it works

1. `npx mcp-aemps@latest` runs this wrapper
2. Wrapper spawns `uvx --from mcp-aemps mcp-aemps stdio` (preferred path)
3. The Python server runs as a stdio MCP server, talking JSON-RPC over
   stdin/stdout — exactly what the client expects

If `uvx` isn't installed, falls back to `pipx run` then `mcp-aemps`
on PATH.

## Why an npm wrapper?

Many MCP clients lean on `npx`-based config snippets. This wrapper makes
the Spanish AEMPS CIMA server feel native to that ecosystem without
forcing users to install Python tooling explicitly — `uv` is fetched on
demand, the Python package on PyPI stays the canonical implementation.

## Override the PyPI version

```bash
MCP_AEMPS_PYPI_VERSION=0.1.6 npx mcp-aemps@latest
```

## License

Apache-2.0 © Román Pérez Dumpert. Source: https://github.com/romanpert/mcp-aemps
