# MCP AEMPS/CIMA Server

> **MOXI MCP Server** — modular, independent, auto-discovered by the agent.

## What

Spanish AEMPS/CIMA drug database (20,000+ authorised medicines, PDFs, presentations, pharmacovigilance notes).

## Source

- **API:** CIMA REST API (`https://cima.aemps.es/cima/rest`)
- **Auth:** None
- **Source Tier:** Tier 1

## Endpoints

- `GET /medicamento`, `GET /medicamentos`
- `GET /presentacion`, `GET /presentaciones`
- `GET /vmpp`, `GET /maestras`
- `GET /documentos` — technical sheets & leaflets (PDF + HTML)
- `GET /datos_locales` — regional pricing/availability
- `GET /vigilancia` — pharmacovigilance notes
- `GET /health` — Health check
- `GET /internal/metrics` — Prometheus metrics (requires `x-metrics-key`)
- `POST /mcp` — MCP protocol (auto-discovered by agent)

## Quick Start

### Standalone

```bash
cd services/mcp_aemps
pip install -r requirements.txt
python -m app.cli dev --port 8000
```

### Docker

```bash
docker build -t mcp_aemps .
docker run -p 8000:8000 mcp_aemps
```

### MOXI stack

```bash
docker compose up -d mcp_server
```

## Swagger

`http://localhost:8000/docs`

## Architecture

Slim FastAPI orchestrator (`app/mcp_aemps_server.py`) wires route modules from `app/routes/`:
`medicamentos`, `presentaciones`, `documentos`, `datos_locales`, `vigilancia`.
Cross-cutting concerns live in `logging_setup`, `otel_setup`, `rate_limits`, `dependencies`.

## License

Part of the MOXI project.
