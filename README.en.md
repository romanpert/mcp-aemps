<p align="center">
  <img src="docs/mcp_aemps_logo_v2.jpg" alt="mcp-aemps" width="180"/>
</p>

<h1 align="center">mcp-aemps</h1>

<p align="center">
  <strong>The first open-source, regulatory-compliant MCP server for the pharmaceutical industry.</strong><br/>
  Real-time access to Spain's AEMPS/CIMA drug registry — 20,000+ authorised medicines, safety alerts, supply problems, clinical documents — as structured MCP tools for any AI assistant.
</p>

<p align="center">
  <a href="README.md">🇪🇸 Español</a> · 🇬🇧 <strong>English</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/mcp-aemps/"><img src="https://img.shields.io/pypi/v/mcp-aemps?color=blue" alt="PyPI"/></a>
  <a href="https://pypi.org/project/mcp-aemps/"><img src="https://img.shields.io/pypi/pyversions/mcp-aemps" alt="Python versions"/></a>
  <a href="https://pypi.org/project/mcp-aemps/"><img src="https://img.shields.io/pypi/dm/mcp-aemps?color=blue" alt="Downloads"/></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-green" alt="License"/></a>
  <a href="https://github.com/romanpert/mcp-aemps/actions/workflows/ci.yml"><img src="https://github.com/romanpert/mcp-aemps/actions/workflows/ci.yml/badge.svg" alt="CI"/></a>
  <a href="https://registry.modelcontextprotocol.io/v0/servers?search=mcp-aemps"><img src="https://img.shields.io/badge/MCP%20Registry-listed-purple" alt="MCP Registry"/></a>
  <img src="https://img.shields.io/badge/CIMA%20API-v1.23-orange" alt="CIMA API v1.23"/>
</p>

> **Note**: mcp-aemps wraps the **Spanish** drug registry (AEMPS / CIMA). The data itself is in Spanish — drug names, technical sheets, leaflets, safety notes are all written in Spanish by the regulator. The English locale (`MCP_AEMPS_LOCALE=en`) translates the LLM-facing **infrastructure** (tool descriptions, prompt bodies, system prompt) but the **content** returned by the API stays in Spanish, since that is the official, source-of-truth language.

---

## What it does

`mcp-aemps` wraps the **AEMPS CIMA REST API** as a full MCP server. Connect Claude, GPT-4o, Gemini — or any MCP-compatible agent — to Spain's official pharmaceutical registry. Query drug authorisations, technical sheets, pharmacovigilance safety notes, supply problems, clinical equivalents, and more, in real time.

**Data source:** [CIMA (AEMPS)](https://cima.aemps.es) — public API, no PII, no authentication required.
**Compliance posture:** Read-only proxy. Audit trail per request. No patient data processed.

---

## Install

```bash
# pip
pip install mcp-aemps

# zero-install (recommended for CLI clients)
uvx mcp-aemps up
pipx run mcp-aemps up

# Docker (multi-arch: linux/amd64, linux/arm64) — minimum 0.1.6
docker run -p 8765:8765 ghcr.io/romanpert/mcp-aemps:latest

# Docker Compose
docker compose up -d
```

---

## One-command client setup

After `pip install mcp-aemps`, register the server with your MCP client in **one command** — no manual JSON editing.

```bash
# All detected clients at once
mcp-aemps install

# Or pick one
mcp-aemps install claude-desktop   # stdio default (uvx auto-launch); HTTP via mcp-remote optional
mcp-aemps install claude-code      # uses `claude mcp add` if available
mcp-aemps install codex
mcp-aemps install vscode           # writes mcp.servers in user settings.json (Copilot Chat MCP)
mcp-aemps install cursor           # writes ~/.cursor/mcp.json
mcp-aemps install windsurf         # writes ~/.codeium/windsurf/mcp_config.json
mcp-aemps install zed              # writes context_servers in Zed settings.json
mcp-aemps install continue         # writes mcpServers in ~/.continue/config.yaml
mcp-aemps install jetbrains        # writes ~/.junie/mcp.json (JetBrains Junie)

# Custom URL or server key
mcp-aemps install --url http://my-host:9000/mcp --name aemps
```

To remove:

```bash
mcp-aemps uninstall                  # remove from all
mcp-aemps uninstall claude-desktop   # one client only
```

**Properties** — installers are *idempotent* (safe to re-run), *additive* (preserves your other entries), *atomic* (write succeeds fully or not at all), and *port-aware* (read the actual port `mcp-aemps up` bound to, so you can change ports without re-installing).

**Per-OS config paths:**

| Client | macOS | Windows | Linux |
|---|---|---|---|
| Claude Desktop | `~/Library/Application Support/Claude/claude_desktop_config.json` | `%APPDATA%\Claude\claude_desktop_config.json` | `~/.config/Claude/claude_desktop_config.json` |
| Claude Code | `claude mcp add` (preferred) → fallback `~/.claude.json` | same | same |
| Codex | `~/.codex/config.toml` | `%USERPROFILE%\.codex\config.toml` | `~/.codex/config.toml` |
| VS Code | `~/Library/Application Support/Code/User/settings.json` | `%APPDATA%\Code\User\settings.json` | `~/.config/Code/User/settings.json` |
| Cursor | `~/.cursor/mcp.json` | same | same |
| Windsurf | `~/.codeium/windsurf/mcp_config.json` | same | same |
| Zed | `~/.config/zed/settings.json` | `%APPDATA%\Zed\settings.json` | `~/.config/zed/settings.json` |
| Continue.dev | `~/.continue/config.yaml` | same | same |
| JetBrains Junie | `~/.junie/mcp.json` | same | same |

After install, **start the server** (default port: **`8765`** — chosen to avoid collisions with the very common `8000`/`5000`/`3000`):

```bash
mcp-aemps up           # foreground
mcp-aemps up --daemon  # background
mcp-aemps up --port 9000  # explicit port; auto-fallback enabled by default
```

Then restart your client. `mcp-aemps` appears as an available MCP server.

---

## MCP Tools — Official CIMA Endpoints

All tools map 1:1 to officially documented CIMA REST API endpoints.

| Tool | CIMA Endpoint | Description |
|------|--------------|-------------|
| `obtener_medicamento` | `GET /medicamento` | Full drug record by CN or nregistro |
| `buscar_medicamentos` | `GET /medicamentos` | Filtered/paginated drug search (20+ filters) |
| `buscar_en_ficha_tecnica` | `POST /buscarEnFichaTecnica` | Full-text search inside technical sheets |
| `listar_presentaciones` | `GET /presentaciones` | Presentations list with filters |
| `obtener_presentacion` | `GET /presentacion/:cn` | Presentation detail by National Code |
| `buscar_vmpp` | `GET /vmpp` | Clinical equivalents (VMP/VMPP) |
| `consultar_maestras` | `GET /maestras` | Master catalogs: ATC, active ingredients, forms, labs |
| `registro_cambios` | `GET\|POST /registroCambios` | Authorization/withdrawal/modification history |
| `problemas_suministro` | `GET /psuministro` + `GET /psuministro/v2/cn/:cn` | Supply problems — global listing or per National Code |
| `problemas_suministro_dcp` | `GET /psuministro/v2/dcp/:dcp` | Supply problems by DCP (clinical product description) |
| `problemas_suministro_dcpf` | `GET /psuministro/v2/dcpf/:dcpf` | Supply problems by DCPF (with pharmaceutical form) |
| `listar_notas` / `obtener_notas` | `GET /notas/:nregistro` | Safety notes |
| `listar_materiales` / `obtener_materiales` | `GET /materiales/:nregistro` | Safety informational materials |
| `doc_secciones` | `GET /docSegmentado/secciones/:tipo` | Technical sheet / leaflet section metadata |
| `doc_contenido` | `GET /docSegmentado/contenido/:tipo` | Section content (JSON / HTML / plain text) |
| `html_ficha_tecnica` | `GET /dochtml/ft/:nregistro/:file` | Full technical sheet HTML |
| `html_prospecto` | `GET /dochtml/p/:nregistro/:file` | Full patient leaflet HTML |

Supply problems implement **dual-channel resolution**: v2 per-CN (enriched: authorization status, comercialisation flag) with automatic fallback to v1 for compatibility.

---

## Data Lifecycle

- **No local files required.** All data fetched from CIMA API on demand.
- **Redis cache** (optional): startup warm-up for master catalogs (maestras), automatic 24h refresh — no app restart needed.
- **CN → nregistro resolution** via `GET /presentacion/:cn` (always current, no stale local data).
- Falls back gracefully to in-memory cache when Redis is unavailable.

---

## Configuration

All settings via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8765` | Server port (`mcp-aemps up --auto-port` finds free if busy) |
| `REDIS_URL` | — | Redis or Valkey connection (optional, enables distributed cache + rate limit) |
| `ALLOWED_ORIGINS` | `http://localhost:3000` | CORS origins (do not use `*` in production) |
| `METRICS_KEY` | — | If set, `/internal/metrics` requires the `X-Metrics-Key` header. Recommended in production. |
| `LOG_LEVEL` | `INFO` | Logging level |
| `LOG_RETENTION_DAYS` | `90` | Daily-rotated gzipped log retention |
| `MAX_RESULTS` | `30` | Max items per page returned by list endpoints |
| `MCP_AEMPS_LOCALE` | auto | LLM-facing language: `es` or `en`. Auto-detected from `$LANG`/`$LC_ALL` if unset (default `es`). |
| `OAUTH_ENABLED` | `false` | Enable OAuth 2.1 Resource-Server mode. See OAuth section. |

---

## Observability

Ships with **lightweight in-process observability** — no external collector required:

- **Liveness** at `/health/live` — process is alive (always 200 if the event loop responds).
- **Readiness** at `/health/ready` — cache backend reachable AND maestras warmup completed (returns 503 during startup). Wire this into Kubernetes `readinessProbe`.
- **Combined snapshot** at `/health` — `{status, version, cache}` JSON (kept for backwards compatibility).
- **In-process metrics** at `/internal/metrics` — `{requests_total, requests_by_path, status_codes, errors_5xx, uptime_seconds}` JSON. Set `METRICS_KEY` to require the `X-Metrics-Key` header.
- **Structured stdlib logging** with daily rotation + gzip retention.

For OpenTelemetry tracing or Prometheus exposition, replace the metrics middleware via the factory's `extra_middleware` / `startup_hooks` extension points (see `app/factory.py`).

---

## Language (i18n)

LLM-facing strings (tool descriptions, system prompt, prompt descriptions and bodies) ship in **Spanish (default)** and **English**. Switch with the `MCP_AEMPS_LOCALE` env var:

```bash
# Default — auto-detected from OS; no env var → es
uvx mcp-aemps stdio

# Explicit English (always wins over OS sniff)
MCP_AEMPS_LOCALE=en uvx mcp-aemps stdio
```

Since v0.2.11 the **OS locale is auto-detected** (`$LC_ALL` / `$LANG` / `$LANGUAGE`): English-tagged systems get `en`, everything else (including the POSIX `C` locale and unrecognised locales) falls back to `es` because CIMA's source data is Spanish. An explicit `MCP_AEMPS_LOCALE` always wins over the auto-detection.

Since v0.2.9 the **full** prompt catalogue (descriptions + bodies + patient-facing disclaimer) ships in both locales. Both locales register the same 10 prompt names with the same arg signatures — clients hard-coding prompt names keep working when you flip the locale.

---

## OAuth 2.1 (opt-in)

mcp-aemps is **public by default** because CIMA itself is public. For multi-tenant SaaS deployments or any setup where you need to gate access, the server can be flipped into **OAuth 2.1 Resource-Server** mode with five env vars:

```bash
export OAUTH_ENABLED=true
export OAUTH_ISSUER=https://auth.example.com
export OAUTH_JWKS_URL=https://auth.example.com/.well-known/jwks.json
export OAUTH_AUDIENCE=https://mcp-aemps.example.com/mcp
export OAUTH_REQUIRED_SCOPES=mcp:read
```

When enabled:

* Every MCP tool call over HTTP at `/mcp` requires a valid Bearer JWT signed by the configured Authorization Server.
* The PRM document is published at `/.well-known/oauth-protected-resource` (RFC 9728), so any spec-compliant MCP client can discover the AS via Dynamic Client Registration (RFC 7591).
* stdio is unaffected — process-local access is gated by OS permissions, not by OAuth.

**No embedded Authorization Server.** Point `OAUTH_ISSUER` at any existing IdP — Auth0, Stytch, Cloudflare Workers OAuth Provider, Hydra, Keycloak, etc. mcp-aemps stays stateless: it verifies tokens, never issues them.

Validated end-to-end in v0.2.10: POST `/mcp` without a token returns 401 with `WWW-Authenticate: Bearer error="invalid_token", resource_metadata="<PRM URL>"` (RFC 6750 §3 + RFC 9728).

---

## Tool Annotations

Every CIMA tool ships with the [MCP tool annotations](https://blog.modelcontextprotocol.io/posts/2026-03-16-tool-annotations/) that compliant clients (Claude Desktop, ChatGPT Dev Mode, Cursor, Continue, Zed, JetBrains Junie, …) use to drive their auto-approve UI:

| Hint              | Value | Reason                                                      |
|-------------------|-------|-------------------------------------------------------------|
| `readOnlyHint`    | true  | The server is a thin proxy — no writes upstream.            |
| `destructiveHint` | false | No environment mutations, ever.                             |
| `idempotentHint`  | true  | Same args at the same instant return the same payload.      |
| `openWorldHint`   | true  | Tools hit the external CIMA HTTP API.                       |

This means clients that respect the spec will not prompt for confirmation on every CIMA query — they only gate calls where the annotations actually warrant caution. For Claude Code specifically, see below to build your own confirmation gates regardless of annotation hints.

---

## Curated MCP Resources

mcp-aemps exposes **5 static resources + 6 templates** under the `cima://` URI scheme. Resources are read-only URIs that MCP clients can **stream** and **cache** without paying the token cost of a tool call — the dominant token waste on interactive sessions.

### Static resources (auto-discoverable in `resources/list`)

| URI | MIME | Content |
|---|---|---|
| `cima://maestras/atc` | `application/json` | Full ATC code tree |
| `cima://maestras/principios-activos` | `application/json` | Full list of active substances |
| `cima://maestras/laboratorios` | `application/json` | Marketing-authorisation holders registered with AEMPS |
| `cima://maestras/formas-farmaceuticas` | `application/json` | Pharmaceutical forms (tablet, injection, …) |
| `cima://maestras/vias-administracion` | `application/json` | Routes of administration (oral, IV, topical, …) |

### Templates (`resources/templates/list`)

| URI template | Content |
|---|---|
| `cima://maestras/atc/{codigo}` | Lookup ATC by code (e.g. C09AA02 → Enalapril) |
| `cima://maestras/principios-activos/{id}` | Lookup active substance by AEMPS id |
| `cima://docs/ficha-tecnica/{nregistro}` | Full SmPC HTML |
| `cima://docs/ficha-tecnica/{nregistro}/{seccion}` | Specific SmPC section (4.1, 4.8, 5.1, …) |
| `cima://docs/prospecto/{nregistro}` | Full patient leaflet HTML |
| `cima://docs/prospecto/{nregistro}/{seccion}` | Specific leaflet section (1, 2, 3, 4, 5, 6) |

Available on **both transports** (stdio and `/mcp` HTTP) — since v0.2.7 a single `FastMCP` server serves tools, prompts and resources for both sides.

---

## Curated MCP Prompts

mcp-aemps ships **10 curated [MCP Prompts](https://modelcontextprotocol.io/specification/server/prompts)** — server-defined workflow templates you invoke explicitly from your MCP client (Claude Desktop, Continue, Cursor, Zed, …). They orchestrate the right CIMA tool calls for the most common professional and patient workflows, so you don't have to remember which tools to chain.

> **Transport availability**: Prompts ship on **both** transports — stdio (`uvx mcp-aemps stdio`) and Streamable HTTP at `/mcp`. Since v0.2.7 the HTTP transport uses FastMCP's native Streamable-HTTP app (no fastapi-mcp indirection), so tools, prompts, resources and annotations are all served from the same FastMCP instance.

### Catalogue

| Prompt | Args | Use case |
|---|---|---|
| **`identificar_cn`** | `cn` | **Community pharmacy** — patient brings a box with a National Code; one-screen summary card with authorisation, marketing, prescription, active alerts, supply, official photos and links to AEMPS documentation. |
| **`equivalencias_genericas`** | `nregistro`, `comercializados_solo?` | **Community pharmacy** — substitution during a shortage. Same active substance + dose + dosage form, with box photo to visually confirm. |
| **`vigilancia_paciente`** | `nregistros[]` | **Hospital pharmacy** — review of active safety notes for a patient's medication list. Aligned with EMA GVP Module VI. |
| **`comparar_fichas_tecnicas`** | `nregistros[]`, `secciones?` | **Hospital + industry** — wide-format table comparing 2-5 medicines section by section of the SmPC (4.1, 4.2, 4.3, 4.4, 4.5, 4.8 by default). |
| **`auditar_cartera_laboratorio`** | `laboratorio`, `incluir_no_comercializados?` | **Industry** — complete regulatory snapshot of a manufacturer: global metrics, therapeutic areas (ATC), black triangle, top with active notes, supply risks, IPT presence. |
| **`monitorizar_cambios_cartera`** | `nregistros[]`, `desde_fecha?` | **Industry · regulatory affairs** — detects changes (addition, removal, SmPC/leaflet/marketing/safety-note modification) over a list of products in a period. |
| **`informe_posicionamiento_terapeutico`** | `nregistro` | **Hospital + industry** — retrieves the AEMPS Public Assessment Report (IPE/IPT) along with the authorised indication (SmPC 4.1) and the mechanism of action (SmPC 5.1). Explicitly flags when AEMPS has not published an IPT. |
| **`material_visual_paciente`** | `nregistro` | **Patient counseling** — photos of the box and the dosage form, instruction videos (inhalers, insulin pens, autoinjectors), informational material segregated by audience. Closes with disclaimer. |
| **`info_medicamento_para_no_sanitarios`** | `nombre_o_cn` | **General public** — plain summary without jargon: what it is, what it is used for, what it looks like (photos), active alerts, where to read more. Closes with mandatory "not medical advice" disclaimer. |
| **`comprobar_interaccion_principios_activos`** | `principios_activos[]` | **Hospital pharmacy + industry** — checks whether section 4.5 (Interactions) of AEMPS SmPCs mentions cross-interactions between 2-5 active substances. Textual search over official documentation; **does NOT replace a formal clinical interaction-checking tool** (BOT PLUS, Lexicomp, Stockley, Micromedex). |

### How to invoke

In Claude Desktop (when the client supports it), they appear as `/mcp__mcp-aemps__<name>` slash-commands in the prompts menu, or can be listed via `prompts/list` from any MCP-compliant client.

Programmatic example with the Python MCP SDK:

```python
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp import ClientSession

params = StdioServerParameters(command="uvx", args=["mcp-aemps", "stdio"])
async with stdio_client(params) as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()
        prompts = await session.list_prompts()
        result = await session.get_prompt(
            "identificar_cn",
            arguments={"cn": "12345"},
        )
        # result.messages[0].content.text → the prompt body ready to send to the LLM
```

### Design

Each prompt instructs the LLM **which tools to call, in what order, and how to format the output**. They leverage the rich payload of `obtener_medicamento` (which includes `docs[]` with SmPC, Leaflet, Public Assessment Report and Risk Management Plan; `fotos[]` with the box and dosage form; the `materialesInf` flag for videos via `obtener_materiales`) instead of treating CIMA as a thin field lookup.

The **patient-facing** prompts (`material_visual_paciente`, `info_medicamento_para_no_sanitarios`, `comprobar_interaccion_principios_activos`) always close with an explicit "not medical advice — consult your doctor or pharmacist" disclaimer. It is covered by test (`tests/test_prompts.py`); accidental removal breaks CI.

---

## Integrating with Claude Code hooks

Claude Code's [hooks system](https://docs.anthropic.com/claude-code/hooks) fires shell commands client-side around every tool invocation, including calls to MCP servers like mcp-aemps. The matcher `mcp__mcp-aemps__*` catches every tool exposed by this server. Three concrete recipes to drop into `~/.claude/settings.json`:

### 1 · Audit every mcp-aemps call to a JSONL log

Useful for GMP Annex 11 / EMA GVP audit trails — full record of which tool was invoked with which arguments, when, by which session.

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "mcp__mcp-aemps__.*",
        "hooks": [
          {
            "type": "command",
            "command": "jq -c '{ts: now, session: .session_id, tool: .tool_name, args: .tool_input}' >> ~/.claude/audit/mcp-aemps.jsonl"
          }
        ]
      }
    ]
  }
}
```

The hook receives the tool call as JSON on stdin; `jq` flattens it to one line per call. Rotate `~/.claude/audit/` with `logrotate` or your SIEM agent.

### 2 · Gate image downloads behind explicit confirmation

`descargar_imagenes` returns base64-encoded medication images that can be large and bandwidth-expensive. Block the call unless the user has opted in via an env-var flag.

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "mcp__mcp-aemps__descargar_imagenes",
        "hooks": [
          {
            "type": "command",
            "command": "[ \"$MCP_AEMPS_ALLOW_IMAGES\" = '1' ] || { echo 'Set MCP_AEMPS_ALLOW_IMAGES=1 to authorise image downloads' >&2; exit 2; }"
          }
        ]
      }
    ]
  }
}
```

Exit code `2` aborts the tool call and returns the stderr message to the model — Claude Code surfaces it as a denied tool with reason.

### 3 · Ship per-tool latency to a SIEM

Pair `PreToolUse` (timer start) with `PostToolUse` (timer stop) and POST the delta plus tool name to your SIEM ingestion endpoint.

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "mcp__mcp-aemps__.*",
        "hooks": [
          { "type": "command", "command": "date +%s%N > /tmp/mcp-aemps.start" }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "mcp__mcp-aemps__.*",
        "hooks": [
          {
            "type": "command",
            "command": "END=$(date +%s%N); START=$(cat /tmp/mcp-aemps.start); ELAPSED_MS=$(( (END - START) / 1000000 )); jq -c --arg ms \"$ELAPSED_MS\" '{ts: now, tool: .tool_name, latency_ms: ($ms|tonumber), success: (.tool_response.error == null)}' | curl -sS -X POST -H 'content-type: application/json' --data-binary @- https://siem.example.com/ingest/mcp"
          }
        ]
      }
    ]
  }
}
```

> **Server-side equivalent.** mcp-aemps also exposes `pre_tool_hooks` / `post_tool_hooks` on `create_app(...)` so the same audit trail can be emitted server-side regardless of which MCP client is connected (useful for shared deployments where you can't rely on every user having the right `~/.claude/settings.json`). See `app/tool_hooks.py`.

---

## Security

- Non-root Docker user (UID 10001)
- Security headers: `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`
- `pyjwt[crypto]` — no `python-jose` (CVE-2024-33663)
- No secrets in repo — all config via env vars
- CORS configurable, not `*` in production

---

## Reference Documentation

Official AEMPS source documents in [`docs/`](docs/):

- [`CIMA_REST_API.pdf`](docs/CIMA_REST_API.pdf) — CIMA REST API v1.23
- [`CIMA-problemas-suministro.pdf`](docs/CIMA-problemas-suministro.pdf) — Supply Problems API (AEMPS / Spanish Ministry of Health)

---

## License

Apache-2.0 © [Román Pérez Dumpert](https://github.com/romanpert)

<!-- MCP Registry ownership marker — DO NOT REMOVE -->
<sub><sup>mcp-name: io.github.romanpert/mcp-aemps</sup></sub>
