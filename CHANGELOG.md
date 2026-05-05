# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.2] — 2026-05-05

### Added
- **One-command client install** — `mcp-aemps install [claude-desktop|claude-code|codex]`
  auto-configures the server in any MCP-compatible client. Idempotent, preserves
  existing entries in the user's config. Per-OS path resolution.
- `mcp-aemps uninstall` to remove the server cleanly from clients.
- Test suite: 14 hermetic tests covering installers and end-to-end factory boot
  (Claude Desktop, Claude Code, Codex, lifespan hooks, extra routers).
- `CONTRIBUTING.md` with GitFlow workflow, conventional-commit standards, and
  PR/issue templates.
- `SECURITY.md` with threat model, self-imposed rate-limit policy, and hardening
  checklist for production.

### Changed
- CLI script renamed: `mcp_aemps` → `mcp-aemps` (single canonical command).
  Underscore alias removed.
- CI pipeline now runs the full pytest suite on Python 3.11/3.12/3.13 instead of
  an inline smoke test.
- Lint baseline is clean (ruff, 0 findings).

## [0.1.1] — 2026-05-05

### Added
- README ownership marker (`mcp-name: io.github.romanpert/mcp-aemps`) required
  by the official MCP Registry to validate PyPI package ownership.

## [0.1.0] — 2026-05-05

First public release.

### Added
- MCP tools for every officially documented CIMA REST API v1.23 endpoint:
  `/medicamento`, `/medicamentos`, `/buscarEnFichaTecnica`, `/presentacion(es)`,
  `/vmpp`, `/maestras`, `/registroCambios`, `/notas`, `/materiales`,
  `/docSegmentado/*`, `/dochtml/*`.
- Supply-problems dual-channel: `/psuministro` (v1 global), `/psuministro/v2/cn/{cn}`
  (v2 enriched with automatic v1 fallback on 404), `/psuministro/v2/dcp/{cod_dcp}`
  and `/psuministro/v2/dcpf/{cod_dcpf}` (AEMPS Problemas Suministro API v1.01).
- `create_app()` factory (`app.factory`) — public extension API for downstream
  editions to inject extra routers, middleware, and lifecycle hooks.
- Composable lifespan (`app.lifespan`) with explicit startup/shutdown hook lists.
- Cache backend abstraction (`app.cache`) — `cachetools.TTLCache` in-memory by
  default, automatic Redis backend when `REDIS_URL` is configured.
- Rate limiting via `limits` library — in-memory by default, Redis-backed when
  `REDIS_URL` is set. Three tiers: local (60/min), standard (30/min), heavy (12/min).
- Streamable HTTP MCP transport at `/mcp` (via `fastapi-mcp`).
- Typer CLI (`mcp_aemps up | dev | down | status | restart | logs | health | docs | openapi`).
- Live CN → nregistro resolution via CIMA `/presentacion/{cn}` (no local Excel files).
- Maestras warm-up and 24h periodic refresh — no app restart required.

### Security
- Non-root Docker user (UID 10001).
- Configurable CORS (no `*` by default in production configs).
- Security headers: `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`,
  `Permissions-Policy`.
- No PII processed: CIMA exposes medicine metadata only.

[0.1.2]: https://github.com/romanpert/mcp-aemps/releases/tag/v0.1.2
[0.1.1]: https://github.com/romanpert/mcp-aemps/releases/tag/v0.1.1
[0.1.0]: https://github.com/romanpert/mcp-aemps/releases/tag/v0.1.0
