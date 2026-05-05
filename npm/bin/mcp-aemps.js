#!/usr/bin/env node
// mcp-aemps — npm wrapper that delegates to the Python implementation.
//
// We don't reimplement the MCP server in TypeScript: we ship the canonical
// Python implementation (https://pypi.org/project/mcp-aemps/) and use uv's
// `uvx` runner to fetch + execute it transparently. Users get:
//
//     npx mcp-aemps@latest             -> defaults to stdio (canonical MCP)
//     npx mcp-aemps@latest stdio       -> explicit stdio
//     npx mcp-aemps@latest up          -> HTTP server on :8765
//     npx mcp-aemps@latest install ... -> client auto-config
//
// Forwards stdin/stdout/stderr verbatim so JSON-RPC messages flow through
// untouched when used as a stdio MCP server.

import { spawn } from "node:child_process";
import process from "node:process";

const args = process.argv.slice(2);

// Default to `stdio` when the wrapper is invoked with no subcommand
// (canonical MCP usage from Claude Desktop / Codex / Cursor / Windsurf).
if (args.length === 0) {
  args.push("stdio");
}

const PYPI_PIN = process.env.MCP_AEMPS_PYPI_VERSION ?? "latest";
const pkgSpec = PYPI_PIN === "latest" ? "mcp-aemps" : `mcp-aemps==${PYPI_PIN}`;

function tryRun(cmd, cmdArgs) {
  return new Promise((resolve) => {
    const child = spawn(cmd, cmdArgs, { stdio: "inherit", shell: false });
    child.on("error", (err) => resolve({ ok: false, err }));
    child.on("exit", (code) => resolve({ ok: true, code: code ?? 0 }));
  });
}

(async function main() {
  // 1. uvx (preferred — fast, isolated, no global state)
  const uvxArgs = ["--from", pkgSpec, "mcp-aemps", ...args];
  let result = await tryRun("uvx", uvxArgs);
  if (result.ok) process.exit(result.code);

  // 2. Fallback: pipx run
  result = await tryRun("pipx", ["run", "--spec", pkgSpec, "mcp-aemps", ...args]);
  if (result.ok) process.exit(result.code);

  // 3. Last resort: pip-installed mcp-aemps already on PATH
  result = await tryRun("mcp-aemps", args);
  if (result.ok) process.exit(result.code);

  process.stderr.write(
    [
      "mcp-aemps: could not launch the Python implementation.",
      "",
      "Tried in order:",
      `  1. uvx --from ${pkgSpec} mcp-aemps ${args.join(" ")}`,
      `  2. pipx run --spec ${pkgSpec} mcp-aemps ${args.join(" ")}`,
      `  3. mcp-aemps ${args.join(" ")}  (assumes pip-installed)`,
      "",
      "Install one of:",
      "  - uv:   https://docs.astral.sh/uv/getting-started/installation/  (recommended)",
      "  - pipx: https://pipx.pypa.io/stable/installation/",
      "  - pip:  pip install mcp-aemps",
      "",
    ].join("\n"),
  );
  process.exit(127);
})();
