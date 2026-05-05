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

# zero-install
uvx mcp-aemps up
pipx run mcp-aemps up

# Docker
docker run -p 8000:8000 ghcr.io/romanpert/mcp-aemps:latest

# Docker Compose
docker compose up -d
```

---

## Connect to Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "aemps": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

Then start the server:

```bash
mcp_aemps up
```

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
| `PORT` | `8000` | Server port |
| `REDIS_URL` | — | Redis connection (optional, enables caching) |
| `ALLOWED_ORIGINS` | `http://localhost:3000` | CORS origins |
| `METRICS_KEY` | — | Auth key for `/internal/metrics` |
| `LOG_LEVEL` | `INFO` | Logging level |
| `RATE_LIMIT` | `100` | Requests per period |
| `RATE_PERIOD` | `60` | Period in seconds |

---

## Observability

- **Structured JSON logging** with correlation IDs per request
- **OpenTelemetry** tracing (OTLP export)
- **Prometheus metrics** at `/internal/metrics` (protected by `x-metrics-key`)
- **Health check** at `/health`

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
