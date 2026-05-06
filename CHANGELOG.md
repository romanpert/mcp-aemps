# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.5] — 2026-05-06

### Added
- **MCP tool annotations on all 21 tools** (`readOnlyHint`,
  `destructiveHint=false`, `idempotentHint`, `openWorldHint`). Compliant
  clients (Claude Desktop, ChatGPT Dev Mode, Cursor, Continue, Zed,
  JetBrains Junie, Codex …) now surface CIMA tools as safe reads
  instead of treating every call as potentially destructive — fixes
  the "shows up as a write tool in ChatGPT Dev Mode" UX paper-cut.
  Annotations are mutated post-construction on the HTTP transport
  because `fastapi-mcp` 0.4.x doesn't propagate them from OpenAPI;
  stdio uses `FastMCP`'s native `annotations=` kwarg.
- **README · Tool Annotations** section documents the per-hint
  rationale.
- **README · Integrating with Claude Code hooks** section ships three
  copy-pasteable recipes against the `mcp__mcp-aemps__*` matcher:
  JSONL audit log (GMP Annex 11 / EMA GVP friendly), env-flag-gated
  `descargar_imagenes`, and per-tool latency POST to a SIEM. Plus a
  pointer to the server-side `pre_tool_hooks` / `post_tool_hooks`
  equivalent for shared deployments.

### Fixed
- `app/factory.py` ruff E402 — route imports were below the module-level
  `logger` assignment. Moved imports above so the import block is
  contiguous and `ruff check app/` is clean.

### Tests
- 65/65 passing (was 63). New invariants in
  `tests/test_stdio_server.py` pin annotation values across both
  transports — drift now fails CI.

## [0.2.4] — 2026-05-06

### Added
- **Pre/post tool-call hooks** on both transports. Pass `pre_tool_hooks` /
  `post_tool_hooks` to `create_app(...)` and `build_server(...)`; the same
  hook fires for the same tool name across HTTP and native stdio. Pre-hooks
  raising `OperationError` abort the call with the transport-native error
  shape; post-hooks are best-effort (exceptions logged, never raised). New
  module `app/tool_hooks.py` documents the contract — `HookSet`,
  `PreHookFn`, `PostHookFn`, `wrap_stdio_tool`.
- **`health_extra` extension point** on `/health/ready`. Pass an async
  callable to `create_app(health_extra=...)`; its dict is merged into the
  response body. Any returned key suffixed `_ready` (or the bare key
  `ready`) whose value is `False` flips the response to 503 with
  `status="degraded"`. Probes never crash: a buggy `health_extra` is caught
  and surfaced as `health_extra_error: true`.
- **`metrics_replace` flag** on `create_app(...)`. When true, the
  in-process metrics middleware is skipped so a downstream consumer can
  install Prometheus / OTel instrumentation without double-counting
  requests.

### Changed
- `app.rate_limits` now declares an explicit `__all__` so the per-tier
  Depends helpers (`limit_local`, `limit_standard`, `limit_document`,
  `limit_heavy`) are part of the documented public API. Renaming or
  removing a tier from now on requires a MINOR bump.
- `app/stdio_server.py` `_serialize_errors` replaced by
  `app.tool_hooks.wrap_stdio_tool`. Behaviour for callers without hooks is
  identical: `OperationError` → dict; everything else propagates.

### Tests
- 63/63 passing (was 48). New `tests/test_tool_hooks.py` covers both
  success and error paths for every new surface: pre-hook abort,
  post-hook success/exception swallowing, `health_extra` 200 / 503 /
  buggy-callable, `metrics_replace` on/off, public re-exports.

## [0.2.3] — 2026-05-05

### Added
- **Three new client installers**: `mcp-aemps install zed`,
  `mcp-aemps install continue` (Continue.dev), and
  `mcp-aemps install jetbrains` (JetBrains Junie). All idempotent +
  atomic + per-OS path resolution. Installer registry test enforces
  install/uninstall symmetry from now on.
- **`uninstall_codex`** to close the install/uninstall asymmetry.
- **`/health/live`** (liveness — always 200 if the event loop is
  responsive) and **`/health/ready`** (readiness — 503 until cache
  backend ok and maestras warmup finished). `/health` kept as a
  backwards-compatible snapshot. Wire `/health/ready` into Kubernetes
  `readinessProbe`.
- **`METRICS_KEY` enforcement** on `/internal/metrics`: when set, the
  endpoint requires a matching `X-Metrics-Key` header (401 otherwise).
  When unset, the server logs a warning at startup so production
  deployments do not silently expose counters.

### Changed
- `InMemoryCache` no longer wraps `cachetools.TTLCache` in an
  `asyncio.Lock`. The wrapper does not await between read and write,
  so the lock only added contention. Behaviour identical, fewer
  context switches on hot paths.
- Documentation cleanup: removed all "Enterprise edition", "Full
  edition", "Community Edition" wording from README, SECURITY,
  CONTRIBUTING, CHANGELOG, ROADMAP, code docstrings and issue
  templates. The repository ships the open-source server only;
  downstream consumers extend via the existing factory hooks.
- `SECURITY.md` supported versions bumped to 0.2.x.
- README configuration table updated: documents Redis/Valkey support,
  `METRICS_KEY`, `LOG_RETENTION_DAYS`, `MAX_RESULTS`.

## [0.2.2] — 2026-05-05

### Added
- **`POST /buscarEnFichaTecnica`** — el unico endpoint oficial CIMA que
  faltaba en el transport HTTP ya esta expuesto.
- **stdio expone 5 tools nuevas** que solo estaban en HTTP: `obtener_notas`
  (path-based), `obtener_materiales`, `html_ficha_tecnica_multiple`,
  `html_prospecto_multiple` y la propia `buscar_en_ficha_tecnica`.
- **Test de paridad cross-transport** (`test_http_and_stdio_expose_the_same_tools`)
  que falla el CI si HTTP y stdio divergen.

### Changed
- **Nuevo paquete `app/core/`** como single source of truth: cada
  operacion MCP (medicamentos, presentaciones, VMP/VMPP, maestras,
  registro de cambios, problemas de suministro, notas, materiales,
  documentos) vive como `core_<op>` async function transport-agnostica.
  Los routes FastAPI (`app/routes/*.py`) y las tools FastMCP
  (`app/stdio_server.py`) son adaptadores finos sobre el core.
- **Rutas HTTP ~70% mas cortas**: validacion declarativa via FastAPI
  Query/Path/Body, logica de negocio delegada al core.
- **Errores estructurados**: el core lanza `OperationError(status_code, error,
  message, details)`. Un `@app.exception_handler` global lo serializa a
  `JSONResponse` para HTTP; el stdio lo serializa a dict via decorador
  `_serialize_errors` para que el LLM reciba un payload accionable.
- **Paridad total**: ambos transports exponen las **21 tools CIMA
  oficiales** y devuelven la misma forma JSON.

## [0.2.1] — 2026-05-05

### Changed
- **MCP tool descriptions reescritas y unificadas** a partir de la
  documentacion oficial CIMA REST API v1.23 y Problemas Suministro
  v1.01. Cada herramienta ahora cita su endpoint upstream, sus
  limitaciones (solo medicamentos autorizados en Espana) y un "cuando
  usar" para que los LLMs disambiguen entre tools hermanas (p.ej.
  `obtener_medicamento` vs `buscar_medicamentos`, `doc_contenido` vs
  `html_ficha_tecnica`).
- `mcp_constants.py` es ahora **single source of truth**: las
  descripciones se inyectan tanto en stdio (`@server.tool(description=...)`)
  como en HTTP (`@router.get(..., description=...)`), evitando drift
  entre transports.
- `MCP_AEMPS_SYSTEM_PROMPT` reorganizado por categorias (medicamento
  concreto / presentaciones / catalogos / cambios y vigilancia /
  problemas de suministro / documentos), con un flujo recomendado
  paso a paso.
- `doc_secciones`: el path param `tipo_doc` ahora documenta los 4
  tipos oficiales (1=FT, 2=Prospecto, 3=IPE, 4=Plan Gestion Riesgos)
  en lugar de "3-4 otros".

## [0.2.0] — 2026-05-05

### Added
- **Native stdio MCP transport** (Anthropic-canonical pattern) — new
  `mcp-aemps stdio` command runs the server over stdin/stdout via
  `mcp.server.fastmcp.FastMCP`. 17 official CIMA tools registered.
  Clients now configure us with the universal pattern:
  ```json
  {"command": "uvx", "args": ["mcp-aemps@latest", "stdio"]}
  ```
  No HTTP server, no port management, no `mcp-remote` bridge required.
- **npm wrapper `mcp-aemps`** (unscoped, `npx mcp-aemps@latest`) — thin
  Node.js shim that delegates to the Python implementation via `uvx`,
  with fallback to `pipx run` and pip-installed `mcp-aemps`. Lets users
  who only have Node tooling install us seamlessly. Published with
  npm Trusted Publisher (OIDC) — no token in CI.
- **`.github/workflows/npm.yml`** auto-publishes the npm wrapper on every
  minor release (`vX.Y.0`), synchronised with the Docker image cadence.

### Changed
- **Claude Desktop installer default = stdio** (was: `mcp-remote` HTTP
  bridge). The new entry is `{"command": "uvx", "args":
  ["mcp-aemps@latest", "stdio"]}`. Falls back to the HTTP bridge with
  `install_claude_desktop(transport="http", ...)` if you prefer to
  point Claude Desktop at a long-running shared server.
- 36 tests (was 32) — added stdio tool surface coverage and a transport
  switch test for the Claude Desktop installer.

### Architecture
- New `app/stdio_server.py` — separate transport layer that builds a
  `FastMCP` instance and registers each tool as a thin wrapper over
  `cima_client`. Shares the same `cima_client`, `safe_cima_call`,
  `bounded_gather`, and metadata helpers as the HTTP path, so JSON
  shapes are identical across transports.
- `npm/` directory — TypeScript-free wrapper kept minimal (one Node.js
  script + manifest). Source distributed via `git+https`, so changes
  flow through `git push` like the rest of the codebase.

## [0.1.6] — 2026-05-05

### Fixed
- **Docker multi-arch image was broken** in v0.1.5: the build matrix
  (`linux/amd64`, `linux/arm64`) made each job push to the same tag, the
  last writer winning. Resulting manifest only had `arm64` (`docker pull`
  on x86 returned "no matching manifest for linux/amd64"). Replaced with a
  single Buildx job that emits a real multi-arch manifest list.

## [0.1.5] — 2026-05-05

> **⚠️ Docker users:** the `0.1.5` GHCR image had a broken multi-arch
> manifest (only `linux/arm64` was actually published — `amd64` pulls
> failed with "no matching manifest"). The image was withdrawn on
> 2026-05-05. **Use `0.1.6` or later.** PyPI install was unaffected.

### Added
- **Docker, multi-stage**: new `Dockerfile` (~150 MB final image, was ~280 MB) +
  `.dockerignore`. Non-root UID 10001, healthcheck via curl.
- **`docker-compose.yml`** minimal: server + optional Redis backend (commented).
- **`.github/workflows/docker.yml`** — multi-arch (`linux/amd64`, `linux/arm64`)
  build & push to GHCR on every tag + master, with provenance and SBOM.
  Image: `ghcr.io/romanpert/mcp-aemps:latest`.
- **ETag / If-None-Match revalidation** in `app/cima_client.py` — hot-path
  CIMA queries (`medicamento`, `presentaciones`, `maestras`) now send
  `If-None-Match` against AEMPS's 30-min CDN cache; on 304 we return the
  in-process cached payload without re-parsing. Reduces upstream load by
  ~10× on repeated queries.
- **README badges**: CI status, Python versions, monthly downloads,
  MCP Registry listing.

### Changed
- **Removed dead env vars**: `RATE_LIMIT` and `RATE_PERIOD` were no longer
  used after the v0.1.3 rate-limit refactor. `server.json` env-var list
  trimmed to: `PORT`, `ALLOWED_ORIGINS`, `LOG_LEVEL`, `REDIS_URL`.
- `.gitignore` now covers `.ruff_cache/`, `.mypy_cache/`.

### Architecture
- ETag cache is module-level in `cima_client.py` (bounded LRU at 2048 entries)
  — no Redis required for this layer; per-process is sufficient given CIMA's
  long Cache-Control TTLs.

### Roadmap notes
- **stdio MCP transport** (Anthropic-canonical `uvx mcp-aemps stdio` pattern)
  deferred to v0.1.6 — fastapi-mcp 0.4.0 only exposes HTTP/SSE; needs either
  upstream upgrade or an internal mcp-proxy bridge. Current HTTP transport
  works with all clients via the `mcp-remote` bridge (Claude Desktop) or
  native HTTP support (Claude Code, Codex, VS Code, Cursor, Windsurf).

## [0.1.4] — 2026-05-05

### Added
- **VS Code, Cursor, Windsurf installers** — `mcp-aemps install vscode|cursor|windsurf`.
  Idempotent, atomic, additive. Total clients now: 6 (Claude Desktop, Claude Code,
  Codex, VS Code, Cursor, Windsurf).
- **Lightweight metrics endpoint** — `GET /internal/metrics` returns a JSON
  snapshot (`requests_total`, `requests_by_path`, `status_codes`, `errors_5xx`,
  `uptime_seconds`, `version`). Zero external deps.
- **Runtime port discovery** — `mcp-aemps up/dev` writes the actually-bound
  host:port to a per-user state file (`~/.local/state/mcp-aemps/runtime.json`
  or per-OS equivalent). `mcp-aemps install` reads it automatically — change
  the port without re-installing clients.
- **`.marketing/` directory** (gitignored) — scaffold for launch material.
- 32 tests total (was 19) covering all 6 installers and runtime state.

### Changed
- **Default port: `8000` → `8765`** to avoid collisions with the very
  common 8000 (uvicorn/Django dev), 5000 (Flask), 3000 (Node/Next).
- **Claude Desktop installer fix** — was generating `{"url": "..."}` which
  Claude Desktop **rejects** (its config validator requires stdio entries
  for HTTP MCP servers go through the Connectors UI). Now uses the
  official `mcp-remote` npm bridge: `{"command": "npx", "args": ["-y",
  "mcp-remote", "..."]}`. Fixes "configuración no válida" error.
- CLI: `mcp-aemps up` and `dev` now flag-driven (`--auto-port` / `--no-auto-port`)
  instead of silent fallback. Port-busy fallback is on by default.
- CLI runtime files moved from CWD to per-user state dir
  (`~/.local/state/mcp-aemps/` etc.). No more `.mcp_aemps.pid` polluting cwd.
- CONTRIBUTING.md simplified — dropped the maintainer-only release
  walkthrough (release pipeline is fully automated, no manual steps to share).
- GitHub Actions workflows opt into `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24=true`
  (Node.js 20 is deprecated as of June 2026).

### Architecture

- New module `app/runtime_state.py` — port discovery, state dir resolver,
  free-port scanner. Pure functions, no global state apart from file I/O.
- New module `app/metrics.py` — thread-safe `_Snapshot` counter + ASGI
  middleware. Replaceable by Prometheus / OTel exporters via the factory
  `extra_middleware` / `startup_hooks` extension points.
- `app/installers.py` exposes `ALL_INSTALLERS` / `ALL_UNINSTALLERS`
  registries — CLI subcommands are generated dynamically from these maps,
  no per-client boilerplate to maintain when we add new clients.

## [0.1.3] — 2026-05-05

### Added
- **Rate-limit hardening** based on CIMA API research:
  - New `LIMIT_DOCUMENT` tier (10/min) for HTML/PDF endpoints.
  - New `CIMA_FANOUT_SEMAPHORE` — module-level `asyncio.Semaphore(8)` that
    caps total concurrent CIMA calls server-wide. Single most impactful
    upstream-load defence.
  - New `BATCH_FANOUT_LIMIT = 4` — per-batch-request fan-out cap.
  - `httpx.Limits(max_connections=20, max_keepalive_connections=10)` on the
    CIMA client — bounds the connection pool.
- New helper `bounded_gather` (replaces `asyncio.gather` in batch route handlers)
  to enforce the per-batch concurrency cap.
- Tests: rate-limit tier values, semaphore cap, bounded_gather concurrency.
  Total: 19 tests.

### Changed
- Tier values (per minute, per client IP):
  - `local`: 60 → **120** (no upstream cost)
  - `standard`: 30 (unchanged)
  - `heavy`: 12 → **6** (each request fans out N CIMA calls)
  - `document` (new): **10** for HTML/PDF endpoints
- HTML/PDF document endpoints (`/doc-html/ft`, `/doc-html/p`, single + batch)
  now use the `document` tier instead of `heavy`/`standard`.
- Batch endpoints (`/notas`, `/materiales`, `/problemas-suministro`,
  `/presentacion`, `/doc-html/ft`, `/doc-html/p`) use `bounded_gather` instead
  of unbounded `asyncio.gather`.
- `settings.mcp_aemps_version` now reads from `importlib.metadata` instead of
  a hardcoded "0.1.0" — `/health` and OpenAPI version stay in sync with the
  installed package version automatically.

### Fixed
- `ruff format` baseline applied across the codebase. CI lint check passes
  on both `ruff check` and `ruff format --check`.

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

[0.2.0]: https://github.com/romanpert/mcp-aemps/releases/tag/v0.2.0
[0.1.6]: https://github.com/romanpert/mcp-aemps/releases/tag/v0.1.6
[0.1.5]: https://github.com/romanpert/mcp-aemps/releases/tag/v0.1.5
[0.1.4]: https://github.com/romanpert/mcp-aemps/releases/tag/v0.1.4
[0.1.3]: https://github.com/romanpert/mcp-aemps/releases/tag/v0.1.3
[0.1.2]: https://github.com/romanpert/mcp-aemps/releases/tag/v0.1.2
[0.1.1]: https://github.com/romanpert/mcp-aemps/releases/tag/v0.1.1
[0.1.0]: https://github.com/romanpert/mcp-aemps/releases/tag/v0.1.0
