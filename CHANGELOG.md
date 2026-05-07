# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.2] — 2026-05-07

### Changed

- **Auto-publish trigger policy realigned** across the five
  fully-automated destinations:
  - `release.yml` (PyPI + MCP Registry + GitHub Release with
    `.mcpb`) → every tag (`v*.*.*`).
  - `npm.yml` → every tag (was MINOR-only `vX.Y.0`).
  - `docker.yml` (GHCR) → every tag (was MINOR-only).
  - `docker-mcp-registry.yml` (PR to docker/mcp-registry) →
    MINOR-only `vX.Y.0` (was every tag).
  Rationale: the four OIDC / GITHUB_TOKEN paths are zero-friction
  (no human review), so they should match the canonical PyPI
  cadence one-to-one. The Docker MCP Registry sync is the one
  destination requiring an upstream PR review, so it stays on
  stable-only to avoid spamming reviewers with patch-level noise.
- `bin/mcp-aemps.js` (npm wrapper) defaults to `MCP_AEMPS_PYPI_VERSION=latest`,
  so installations of any npm package version always pull the
  newest PyPI release of `mcp-aemps`. The npm package version is
  packaging metadata; the runtime version follows PyPI.

### Note on the v0.4.1 npm publish

v0.4.1 was tagged before the trigger-policy change, so the
`vX.Y.0` filter excluded it from `npm.yml`'s push-tag event.
Manual `workflow_dispatch` re-firing failed with `ENEEDAUTH`
because npm's Trusted Publisher (OIDC) explicitly rejects
manual dispatches for security reasons (only `push`,
`pull_request`, `release` are eligible). This release closes
the gap by firing the full pipeline via `push: tags:` again.

## [0.4.1] — 2026-05-07

### Fixed

- **MCPB bundle manifest** — added the required `server.mcp_config`
  block (`command: uv`, `args: --directory ${__dirname} run
  server/main.py`, `env` wired to the manifest's `user_config`). The
  v0.4.0 release.yml run failed at the `build-mcpb` step because the
  `@anthropic-ai/mcpb` validator rejects manifests without
  `mcp_config` even for `type: uv` (the CLI is stricter than its own
  docs). All 0.4.0 features are unchanged; this is a release-pipeline
  fix only.
- **`scripts/build_mcpb.sh`** reads/writes the manifest with explicit
  `encoding="utf-8"` and `ensure_ascii=False` so running the build
  locally on Windows (default cp1252) doesn't mojibake the em-dash in
  `display_name` / `long_description`.

## [0.4.0] — 2026-05-07

Anthropic MCP best-practices 2026-Q2 alignment. Skipped `0.3.0` to mark
the breadth of changes — every additive feature flagged by the audit
landed except resource subscriptions, which is held back as a candidate
for the premium / enterprise tier.

### Added

- **Tool titles** (spec tools §205). Every tool now exposes a localised
  display name (`TOOL_TITLES` per locale). Claude Desktop, Inspector,
  Continue and JetBrains Junie render the title in their pickers
  instead of the bare `name`.
- **`logging/setLevel` capability** (spec server/utilities/logging).
  Clients can adjust verbosity at runtime; RFC 5424 levels
  (debug…emergency) are mapped onto the stdlib logger tree via
  `apply_mcp_log_level`. Capability is auto-advertised once the
  handler is registered.
- **`outputSchema` + `structuredContent`** (spec server/tools §"Output
  Schema") on 21/21 tools. New `app/core/schemas.py` declares three
  Pydantic envelopes (`CimaResponse`, `CimaPaginatedResponse`,
  `CimaCollectionResponse`) — typed enough for code-mode hosts
  (Claude Code, Codex CLI) to navigate `metadata` / `resultados` /
  `errors` without re-extracting from a generic dict, permissive
  enough (`extra='allow'`) that upstream CIMA payloads ride through.
  `doc_contenido` was the last holdout; it is now normalised to
  `list[ContentBlock]` so FastMCP auto-wraps a schema while preserving
  the LLM-visible raw HTML/text contract on `format=html|txt`.
- **`resource_link` content blocks** (spec tools §370) emitted by 5
  search/collection tools (`buscar_medicamentos`,
  `listar_presentaciones`, `listar_notas`, `listar_materiales`,
  `problemas_suministro`). Code-mode hosts lazy-resolve hits via
  `cima://medicamento/{nregistro}` / `cima://presentacion/{cn}`
  instead of inlining every full record. TextContent JSON ordering
  preserved so non-code-mode hosts see no wire-format change.
- **Resource templates** `cima://medicamento/{nregistro}` and
  `cima://presentacion/{cn}` — same payload as
  `obtener_medicamento` / `obtener_presentacion`, exposed under the
  `cima://` URI scheme so clients can cache per-id.
- **`completion/complete` handler** (spec server/utilities/completion)
  in `app/completions.py`. Autocomplete for `nregistro`, `cn`,
  `laboratorio`, `principio_activo`, `atc` on prompt arguments and on
  the 7 resource templates. Soft-fail — autocomplete never blocks a
  tool call. `MIN_PREFIX_LEN=2` bounds upstream load.
- **`notifications/progress`** (spec server/utilities/progress) on 4
  fanout tools (`listar_notas`, `listar_materiales`,
  `html_ficha_tecnica_multiple`, `html_prospecto_multiple`). New
  `app.helpers.progress_gather` is a drop-in for `bounded_gather`
  that emits per-item progress when `ctx` carries a `progressToken`,
  degrades cleanly to plain `bounded_gather` when `ctx=None` (HTTP
  transport, tests).
- **MCP Inspector compliance CI job**
  (`.github/workflows/ci.yml::inspector`). Boots uvicorn, runs
  `npx @modelcontextprotocol/inspector --cli` against `tools/list`,
  `prompts/list`, `resources/list`. Asserts ≥ 21 tools with
  non-empty title, description and read-only annotation; ≥ 10 prompts;
  ≥ 1 resource. Catches regressions unit tests miss
  (content-types, missing `_meta`, capability drift).
- **Icons metadata (SEP-973)** in `server.json`. Three sized PNGs
  (64/128/256) under `docs/icons/` referenced via raw GitHub URLs.
  Validates against the 2025-12-11 server schema. FastMCP
  `Implementation` injection deferred until the `mcp` library
  forwards `icons` through `serverInfo`.
- **MCPB bundle** (`mcpb/manifest.json`, `mcpb/server/main.py`,
  `mcpb/pyproject.toml`, `scripts/build_mcpb.sh`). Single-click
  install for Claude for Mac/Windows. Uses the official
  `@anthropic-ai/mcpb` CLI with `type: uv` runtime — the bundle
  pulls `mcp-aemps==<tag>` from PyPI on first launch, so the
  artefact stays small. New `build-mcpb` job in `release.yml`
  attaches the `.mcpb` to every GitHub Release.
- **Claude Code plugin** (`.claude-plugin/`). Three slash commands
  (`/aemps-buscar`, `/aemps-vigilancia`, `/aemps-ficha`) compose
  existing tools and prompts. Bundled `.mcp.json` auto-registers
  `mcp-aemps` via `uvx mcp-aemps stdio` so installing the plugin
  installs the server.

### Changed

- **Trimmed tool descriptions** (audit item 10). ES `13638 → 6474`
  chars (-52.5%); EN `13057 → 6311` (-51.7%). Long examples and
  exhaustive enum tables moved out of upfront-loaded descriptions;
  parameter shape lives in the JSON `inputSchema` (already
  auto-derived from function signatures).
- **`stdio_server.py` no longer uses `from __future__ import annotations`.**
  After `wrap_stdio_tool` applies `functools.wraps`, FastMCP's
  annotation resolver looks names up in the wrapper's `__globals__`
  (= `app.tool_hooks`, which doesn't import the response models).
  Eager (non-stringified) annotations sidestep that lookup.

### Out of scope (deferred / rejected)

- **Resource subscriptions + `notifications/resources/updated`** —
  candidate for the premium / enterprise tier. Real value (push
  pharmacovigilance alerts) but introduces a long-running background
  task; revisited in a separate release.

## [0.2.11] — 2026-05-06

### Added
- **OS-locale auto-detection** for `MCP_AEMPS_LOCALE`. When the env
  var is unset, the server peeks at `$LC_ALL` / `$LANG` /
  `$LANGUAGE` and picks `en` for English-tagged systems, `es` for
  everything else (including the POSIX `C` locale and unrecognised
  locales). An explicit `MCP_AEMPS_LOCALE=es|en` always wins over
  the sniff. CIMA's source data is Spanish, so `es` is the safest
  fallback when no signal is available.
- **New curated MCP Prompt: `comprobar_interaccion_principios_activos`**
  (10th in the catalogue). Checks whether section 4.5 (Interactions)
  of AEMPS SmPCs mentions cross-interactions between 2-5 active
  substances. First prompt to exercise `buscar_en_ficha_tecnica`
  (the textual-search tool was orphan in the prompt catalogue).

  **Safety-critical**: this is patient-facing AND it's an
  interaction-checker, so the body explicitly states it is **NOT a
  substitute** for a formal clinical interaction-checking tool (BOT
  PLUS, Lexicomp, Stockley, Micromedex). A test
  (`test_comprobar_interaccion_warns_about_clinical_tools`) pins
  this — accidental removal of the warning breaks CI.

- **README split** — primary README (`README.md`) is now in
  **Spanish**, since AEMPS is the Spanish regulator and the data
  source is Spanish. Full English translation in `README.en.md`.
  Language selector at the top of both files cross-links them.
  English README adds an explicit note: the i18n locale only
  translates LLM-facing infrastructure (descriptions, prompts);
  the **content** returned by CIMA stays Spanish (drug names,
  technical sheets, leaflets — that's the official source-of-truth
  language).

### Tests
- 127/127 passing (was 114). 13 new tests:
  * 7 OS-locale auto-detect cases (LANG, LC_ALL, LANGUAGE
    permutations + explicit `MCP_AEMPS_LOCALE` override).
  * 6 covering the new interactions prompt: registration on
    catalogue (10 expected names), required-args contract
    (`principios_activos`), body orchestrates
    `buscar_en_ficha_tecnica`, patient-facing disclaimer present,
    edge cases (too-few / too-many active substances), and the
    canonical-tool warning is present.

## [0.2.10] — 2026-05-06

### Validated (no behaviour change)
- **OAuth 2.1 enforcement is real**, not just configured. The v0.2.8
  unit tests covered the `JWKSTokenVerifier` in isolation but never
  proved that FastMCP's `RequireAuthMiddleware` actually invokes it on
  HTTP requests to `/mcp`. v0.2.10 closes that loop with 4 end-to-end
  tests against the mounted `/mcp` endpoint:

  * `POST /mcp` without an Authorization header → **401 + WWW-Authenticate
    header** containing `Bearer error="invalid_token"` and the
    `resource_metadata=` pointer (RFC 6750 §3 + RFC 9728), so
    spec-compliant MCP clients can self-discover the AS.
  * `POST /mcp` with garbage Bearer token → **401**, not 500 — internal
    verifier exceptions never leak.
  * `POST /mcp` with a valid signed JWT → auth layer passes, MCP
    protocol takes over.
  * `POST /mcp` with OAuth disabled (default) → no auth required, no
    regression for public-by-default deployments.

  No code changes were required — the v0.2.8 wiring of `auth=` and
  `token_verifier=` to FastMCP was correct, and the
  `WWW-Authenticate` header is emitted by FastMCP's built-in
  `RequireAuthMiddleware`. v0.2.10 is the proof, not the fix.

### Tests
- 114/114 passing (was 110). 4 new tests in
  `tests/test_i18n_and_auth.py` under the
  `# OAuth 2.1 — end-to-end against /mcp` heading.

## [0.2.9] — 2026-05-06

### Added
- **i18n EN closure** — full English translation of the curated MCP
  Prompts catalogue. Closes the deferred work from v0.2.8 (where only
  tool descriptions and the system prompt were translated; prompt
  bodies stayed Spanish).

  New private modules:
  * `app/_prompts_es.py` — the existing Spanish prompts (content
    unchanged, just relocated and the now-redundant `register_prompts`
    moved to the dispatcher).
  * `app/_prompts_en.py` — full English equivalent: 9 prompt
    functions, `ALL_PROMPTS` tuple with EN descriptions, and the EN
    `PATIENT_FACING_DISCLAIMER`.

  `app/prompts.py` collapses to a 70-line dispatcher that picks one
  module or the other based on `MCP_AEMPS_LOCALE` (same pattern as
  `app/mcp_constants.py` from v0.2.8). `register_prompts(server)`
  lives here and is called once from `build_server()`.

  Behaviour invariants preserved across locales:
  * Same 9 prompt **names** — clients hard-coding prompt names keep
    working when the operator flips the locale.
  * Same arg signatures — required vs optional unchanged.
  * Same workflow steps — both bodies reference the same mcp-aemps
    tools in the same order; only the human-facing language differs.
  * Both patient-facing prompts (`material_visual_paciente`,
    `info_medicamento_para_no_sanitarios`) close with the locale's
    disclaimer ("Aviso legal" in ES, "Legal notice" in EN). The MDR
    2017/745 framing is preserved verbatim.

### Tests
- 110/110 passing (was 106). 4 new tests in
  `tests/test_i18n_and_auth.py`:
  * Spanish module exposes 9 entries with Spanish disclaimer.
  * English module exposes 9 entries with English disclaimer.
  * Both locale modules export the same prompt names (drift fails CI).
  * Body parity spot-check: `identificar_cn` references the same 5
    tools in both languages.

## [0.2.8] — 2026-05-06

### Added
- **i18n EN/ES** — locale-dispatched LLM-facing strings. New env var
  `MCP_AEMPS_LOCALE` (default `es`, accepts `en`) switches every tool
  description, the system prompt, and the `system_info_prompt`
  description from Spanish to English. New private modules
  `app/_mcp_constants_es.py` (the Spanish source of truth, content
  unchanged from v0.2.7) and `app/_mcp_constants_en.py` (functional
  English translation of the full surface). `app/mcp_constants.py`
  collapses to a 50-line dispatcher. **Bodies of the curated prompts
  in `app/prompts.py` stay Spanish** — the routing signal for the LLM
  is the *description*, not the body, so the high-impact translation
  ships first; full body translation deferred.

  Cómo activarlo:
  ```bash
  export MCP_AEMPS_LOCALE=en
  uvx mcp-aemps stdio
  ```
  Existing deployments are unaffected (default `es`).

- **OAuth 2.1 Resource-Server mode (opt-in)** — new module `app/auth.py`
  implementing the RS half of the MCP Authorization spec
  ([modelcontextprotocol.io](https://modelcontextprotocol.io/specification/draft/basic/authorization)).
  When `OAUTH_ENABLED=true`, the HTTP transport at `/mcp` requires a
  valid Bearer token signed by the configured external Authorization
  Server. stdio is unaffected (process-local).

  Implementation details:
  * `JWKSTokenVerifier` validates JWT signature against a remote JWKS
    (RFC 7517, TTL-cached via `pyjwt.PyJWKClient`).
  * Audience (`aud`), issuer (`iss`), expiry (`exp`) and required
    scopes (RFC 6749 `scope` / `scp`) are all enforced.
  * Returns `None` on any failure (malformed token, unknown signing
    key, wrong audience, missing scopes) — never raises.
  * `/.well-known/oauth-protected-resource` (RFC 9728 PRM) exposed
    when OAuth is enabled, advertising the configured AS to
    spec-compliant clients for DCR (RFC 7591) discovery.
  * No embedded Authorization Server — point to your existing IdP
    (Auth0, Stytch, Cloudflare Workers OAuth Provider, Hydra,
    Keycloak, …). Stays stateless.

  New env vars (all required when `OAUTH_ENABLED=true`, otherwise
  ignored):
  * `OAUTH_ENABLED` (bool, default `false`)
  * `OAUTH_ISSUER` — AS issuer URL
  * `OAUTH_JWKS_URL` — JWKS endpoint of the AS
  * `OAUTH_AUDIENCE` — this server's resource indicator (expected
    `aud` claim)
  * `OAUTH_REQUIRED_SCOPES` — comma-separated, default `mcp:read`

  Misconfiguration (`OAUTH_ENABLED=true` without the required vars)
  raises a clear `ValueError` at app-build time, not silently at
  request time.

### Removed
- Decided **NOT** to add EU NCAs (EMA / ANSM / AIFA / BfArM /
  Swissmedic) inside this package. Each NCA has its own response
  format, language and terms of service; a single mega-package would
  be a ball of mud. Each NCA will live in its own PyPI package
  (`mcp-ema`, `mcp-ansm`, …) when implemented, importing mcp-aemps as
  a base library via the existing extension surface
  (`app.factory.create_app(extra_routers=…)`).

### Tests
- 106/106 passing (was 94). New `tests/test_i18n_and_auth.py` covers:
  * Both `_mcp_constants_*` modules export the same public names
    (drift = test failure).
  * Default dispatcher resolves to ES; tool annotations are
    locale-independent.
  * Invalid locale value raises Pydantic `ValidationError` at
    `Settings()` time.
  * OAuth disabled by default → no PRM, public access.
  * OAuth enabled → PRM published with correct content.
  * `JWKSTokenVerifier` accepts a valid signed JWT (in-memory keypair
    + JWKS stub), rejects wrong audience, rejects missing scopes.
  * `OAUTH_ENABLED=true` without `OAUTH_AUDIENCE` raises `ValueError`.

  Tests are written without `importlib.reload` to avoid polluting the
  module cache for the rest of the suite — `monkeypatch.setattr` on
  the live `settings` instance + a JWKS stub at the verifier
  constructor level.

## [0.2.7] — 2026-05-06

### Added
- **MCP Resources** — 5 static + 6 templated resources under the
  `cima://` URI scheme. New module `app/resources.py` +
  `register_resources(server)` integration.

  Static (auto-discoverable via `resources/list`):
  `cima://maestras/{atc,principios-activos,laboratorios,formas-farmaceuticas,vias-administracion}`.

  Templates (`resources/templates/list`):
  `cima://maestras/atc/{codigo}`,
  `cima://maestras/principios-activos/{id}`,
  `cima://docs/ficha-tecnica/{nregistro}[/{seccion}]`,
  `cima://docs/prospecto/{nregistro}[/{seccion}]`.

  Beneficios:
  * **Streaming**: HTML completo de FT/Prospecto fluye al cliente sin
    pasar por una llamada a tool — addresses ROADMAP "Beyond 1.0" item
    #1 (streaming responses for large HTML / leaflet downloads).
  * **Cacheabilidad**: las maestras (ATC, principios activos,
    laboratorios) cambian raramente. Exponerlas como URIs estáticas
    permite a los clientes cachearlas indefinidamente y elimina el
    coste de tokens dominante en sesiones interactivas (llamadas
    repetidas a `consultar_maestras`).
  * **Discoverability**: las URIs estáticas aparecen en la UI de
    Claude Desktop / Continue / Cursor sin que el LLM tenga que
    saber que existen.

### Changed
- **HTTP transport migrado a FastMCP nativo** (Streamable HTTP). La
  capa fastapi-mcp 0.4.x se elimina por completo; el endpoint `/mcp`
  ahora monta directamente el `streamable_http_app()` del FastMCP
  server compartido con stdio. Beneficios:
  * **Single source of truth**: los 21 tools, 9 prompts, 11 resources
    y las anotaciones son el mismo `FastMCP` server detrás de stdio y
    de `/mcp`. Imposible drift entre transportes.
  * **Tool annotations nativas**: ya no se mutan los Tool objects
    post-construcción (era un workaround porque fastapi-mcp 0.4.x no
    propagaba `annotations` desde la ruta OpenAPI).
  * **Prompts y resources en HTTP**: la limitación documentada en
    v0.2.6 ("HTTP no expone prompts") queda resuelta.
  * **Una indirección menos**: las llamadas MCP via HTTP ya no hacen
    un round-trip httpx interno hacia las rutas FastAPI — golpean
    `core_<op>` directamente.
- `app.lifespan.build_lifespan` acepta `fastmcp_server` opcional para
  anidar el `session_manager.run()` del FastMCP en el lifespan exterior
  de FastAPI (necesario porque las sub-apps Starlette montadas no
  ejecutan su lifespan automáticamente).
- `app.stdio_server.build_server` acepta `streamable_http_path` para
  configurar la ruta interna del Streamable-HTTP app (default `/mcp`
  para uso standalone; `create_app` pasa `"/"` para mounting limpio).

### Removed
- Dependencia `fastapi-mcp==0.4.0`. Eliminada de `pyproject.toml` y
  `requirements.txt`. Reduce el árbol de deps y libera futuras
  decisiones de transporte.

### Tests
- 94/94 passing (was 86). 9 nuevos tests en `tests/test_resources.py`
  pinneando el catálogo, MIME types, slugs maestra ↔ id, parámetros
  de templates, validación de input. Reemplazado el test legado
  `test_every_http_tool_has_read_only_annotations` por
  `test_http_transport_uses_the_same_fastmcp_server` que valida que
  HTTP y stdio comparten el mismo `FastMCP` server.

## [0.2.6] — 2026-05-06

### Added
- **9 curated MCP Prompts** — server-defined workflow templates that
  orchestrate the right CIMA tool calls for the most common
  professional and patient flows. New module `app/prompts.py`
  containing the catalogue + `register_prompts(server)` integration.
  Available on the **stdio** transport (`uvx mcp-aemps stdio`); HTTP
  transport via `fastapi-mcp 0.4.x` does not yet expose a prompts
  surface — tracked for v0.3.

  | Prompt | Segmento |
  |---|---|
  | `identificar_cn` | Farmacia comunitaria |
  | `equivalencias_genericas` | Farmacia comunitaria |
  | `vigilancia_paciente` | Farmacia hospitalaria (EMA GVP Module VI) |
  | `comparar_fichas_tecnicas` | Hospital + industria |
  | `auditar_cartera_laboratorio` | Industria · BI / due diligence |
  | `monitorizar_cambios_cartera` | Industria · regulatory affairs |
  | `informe_posicionamiento_terapeutico` | Hospital + industria |
  | `material_visual_paciente` | Counseling al paciente |
  | `info_medicamento_para_no_sanitarios` | Público general |

  Los prompts aprovechan campos del payload de `obtener_medicamento`
  que estaban infrautilizados — `docs[]` (Ficha Técnica, Prospecto,
  Informe Público de Evaluación, Plan de Gestión de Riesgos),
  `fotos[]` (caja + forma farmacéutica) y la combinación
  `materialesInf` + `obtener_materiales` (vídeos de uso para
  inhaladores, plumas de insulina, autoinyectores) — en lugar de
  tratar CIMA como un simple lookup.
- **README · Curated MCP Prompts** documenta el catálogo, la semántica
  por segmento, y muestra un ejemplo de invocación programática con
  el SDK MCP de Python.

### Safety
- Los dos prompts dirigidos a pacientes (`material_visual_paciente`,
  `info_medicamento_para_no_sanitarios`) cierran obligatoriamente con
  un disclaimer "no es consejo médico — consulte a su médico o
  farmacéutico". Cubierto por test; su eliminación accidental rompe
  CI. Marco MDR 2017/745 — este server no es un dispositivo médico.

### Tests
- 86/86 passing (was 65). Nuevo `tests/test_prompts.py` con 21 tests:
  catalog drift, required-args contract, body-orchestrates-tool,
  patient-facing disclaimer, edge-case input validation.

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
