<p align="center">
  <img src="docs/mcp_aemps_logo_v2.jpg" alt="mcp-aemps" width="180"/>
</p>

<h1 align="center">mcp-aemps</h1>

<p align="center">
  <strong>The first open-source, regulatory-compliant MCP server for the pharmaceutical industry.</strong><br/>
  Real-time access to Spain's AEMPS/CIMA drug registry — 20,000+ authorised medicines, safety alerts, supply problems, clinical documents — as structured MCP tools for any AI assistant.
</p>

<p align="center">
  <a href="https://pypi.org/project/mcp-aemps/"><img src="https://img.shields.io/pypi/v/mcp-aemps?color=blue" alt="PyPI"/></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-green" alt="License"/></a>
  <img src="https://img.shields.io/badge/CIMA%20API-v1.23-orange" alt="CIMA API v1.23"/>
  <img src="https://img.shields.io/badge/transport-Streamable%20HTTP-purple" alt="Transport"/>
</p>

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

# Docker
docker run -p 8000:8000 ghcr.io/romanpert/mcp-aemps:latest

# Docker Compose
docker compose up -d
```

---

## One-command client setup

After `pip install mcp-aemps`, register the server with your MCP client in
**one command** — no manual JSON editing.

```bash
# All detected clients at once
mcp-aemps install

# Or pick one
mcp-aemps install claude-desktop   # uses npx mcp-remote bridge (works today)
mcp-aemps install claude-code      # uses `claude mcp add` if available
mcp-aemps install codex
mcp-aemps install vscode           # writes mcp.servers in user settings.json
mcp-aemps install cursor           # writes ~/.cursor/mcp.json
mcp-aemps install windsurf         # writes ~/.codeium/windsurf/mcp_config.json

# Custom URL or server key
mcp-aemps install --url http://my-host:9000/mcp --name aemps
```

To remove:

```bash
mcp-aemps uninstall                  # remove from all
mcp-aemps uninstall claude-desktop   # one client only
```

**Properties** — installers are *idempotent* (safe to re-run), *additive*
(preserves your other entries), *atomic* (write succeeds fully or not at all),
and *port-aware* (read the actual port `mcp-aemps up` bound to, so you can
change ports without re-installing).

**Per-OS config paths:**

| Client | macOS | Windows | Linux |
|---|---|---|---|
| Claude Desktop | `~/Library/Application Support/Claude/claude_desktop_config.json` | `%APPDATA%\Claude\claude_desktop_config.json` | `~/.config/Claude/claude_desktop_config.json` |
| Claude Code | `claude mcp add` (preferred) → fallback `~/.claude.json` | same | same |
| Codex | `~/.codex/config.toml` | `%USERPROFILE%\.codex\config.toml` | `~/.codex/config.toml` |
| VS Code | `~/Library/Application Support/Code/User/settings.json` | `%APPDATA%\Code\User\settings.json` | `~/.config/Code/User/settings.json` |
| Cursor | `~/.cursor/mcp.json` | same | same |
| Windsurf | `~/.codeium/windsurf/mcp_config.json` | same | same |

After install, **start the server** (default port: **`8765`** — chosen to avoid
collisions with the very common `8000`/`5000`/`3000`):

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
| `registro_cambios` | `GET|POST /registroCambios` | Authorization/withdrawal/modification history |
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
| `REDIS_URL` | — | Redis connection (optional, enables caching) |
| `ALLOWED_ORIGINS` | `http://localhost:3000` | CORS origins |
| `METRICS_KEY` | — | Auth key for `/internal/metrics` |
| `LOG_LEVEL` | `INFO` | Logging level |
| `RATE_LIMIT` | `100` | Requests per period |
| `RATE_PERIOD` | `60` | Period in seconds |

---

## Observability

Community Edition ships with **lightweight in-process observability** —
no external collector required:

- **Health check** at `/health` — `{status, version, cache}` JSON snapshot
- **In-process metrics** at `/internal/metrics` — `{requests_total,
  requests_by_path, status_codes, errors_5xx, uptime_seconds}` JSON
- **Structured stdlib logging** with daily rotation + gzip retention

For OpenTelemetry tracing, Prometheus exposition, distributed log
correlation, or audit-grade event streams, use the **Enterprise edition**.

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
- [`CIMA-problemas-suministro.pdf`](docs/CIMA-problemas-suministro.pdf) — Supply Problems API (AEMPS/Ministerio de Sanidad)

---

## Full Version

This is the open-source **Community Edition**. A **Full Edition** is available with extended capabilities for enterprise and regulated environments.

For licensing, integration support, or custom deployments:

**roman.p98@gmail.com**

---

## License

Apache-2.0 © [Román Pérez Dumpert](https://github.com/romanpert)

<!-- MCP Registry ownership marker — DO NOT REMOVE -->
<sub><sup>mcp-name: io.github.romanpert/mcp-aemps</sup></sub>
