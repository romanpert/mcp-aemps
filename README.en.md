<p align="center">
  <img src="https://raw.githubusercontent.com/romanpert/mcp-aemps/master/docs/mcp_aemps_logo_v2.jpg" alt="mcp-aemps" width="180"/>
</p>

<h1 align="center">mcp-aemps</h1>

<!-- mcp-name: io.github.romanpert/mcp-aemps -->

<p align="center">
  <strong>Official pharmaceutical data, ready for your agent.</strong><br/>
  The first open-source MCP server for the pharmaceutical industry. <strong>20,000+ AEMPS-authorised medicines</strong>, real-time, regulator-grade.
</p>

<p align="center">
  <a href="README.md">🇪🇸 Español</a> · 🇬🇧 <strong>English</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/mcp-aemps/"><img src="https://img.shields.io/pypi/v/mcp-aemps?color=blue&label=PyPI" alt="PyPI"/></a>
  <a href="https://www.npmjs.com/package/mcp-aemps"><img src="https://img.shields.io/npm/v/mcp-aemps?color=cb3837&label=npm" alt="npm"/></a>
  <a href="https://github.com/romanpert/mcp-aemps/pkgs/container/mcp-aemps"><img src="https://img.shields.io/badge/ghcr.io-mcp--aemps-2496ed?logo=docker&logoColor=white" alt="GHCR"/></a>
  <a href="https://pypi.org/project/mcp-aemps/"><img src="https://img.shields.io/pypi/pyversions/mcp-aemps" alt="Python versions"/></a>
  <br/>
  <a href="https://pepy.tech/project/mcp-aemps"><img src="https://static.pepy.tech/badge/mcp-aemps" alt="PyPI downloads"/></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-green" alt="License"/></a>
  <a href="https://github.com/romanpert/mcp-aemps/actions/workflows/ci.yml"><img src="https://github.com/romanpert/mcp-aemps/actions/workflows/ci.yml/badge.svg" alt="CI"/></a>
  <a href="https://registry.modelcontextprotocol.io/v0/servers?search=mcp-aemps"><img src="https://img.shields.io/badge/MCP%20Registry-listed-purple" alt="MCP Registry"/></a>
  <img src="https://img.shields.io/badge/CIMA%20API-v1.23-orange" alt="CIMA API v1.23"/>
</p>

> mcp-aemps wraps the **Spanish** drug registry (AEMPS / CIMA). Names, technical sheets, leaflets and safety notes are written in Spanish by the regulator. The English locale (`MCP_AEMPS_LOCALE=en`) translates the **infrastructure** (tool descriptions, prompt bodies, system prompt) — the **content** stays in Spanish, the source-of-truth language.

---

## What your agent can do

Connect Claude, ChatGPT, Gemini, Cursor, Continue, Zed, Junie — or any MCP-compatible agent — to Spain's official AEMPS / CIMA medicines registry. No scrapers. No hardcoded snapshots. No patient data. Every answer cites the official REST endpoint and timestamp.

> **You:** "What serious adverse events appear in the technical sheet of **HUMIRA 40 mg**?"
> **Your agent** queries `obtener_medicamento` → `doc_contenido` (SmPC §4.8) → returns it structured, with timestamp and AEMPS source.

> **You:** "List active supply problems for **omeprazole 20 mg capsules**."
> **Your agent** calls `problemas_suministro_dcpf` → returns affected lots, expected resolution dates, and equivalent therapeutic alternatives.

> **You:** "What pharmacovigilance notes has AEMPS published on **SGLT2 inhibitors** in the last 6 months?"
> **Your agent** filters `listar_notas` + retrieves `obtener_notas` → actionable summary with official links.

> **You:** "Find a clinical equivalent (same VMP) of **simvastatin 20 mg tablets** without lactose."
> **Your agent** crosses `buscar_vmpp` + `buscar_en_ficha_tecnica("lactose")` → proposes alternatives with current AEMPS authorisation and confirmed excipients.

> **You:** "What changed between the current SmPC of **Eliquis** and the version published 90 days ago?"
> **Your agent** invokes the curated `monitorizar_cambios_cartera` prompt → section-by-section diff over the official documentation.

10 more curated prompts, covering community pharmacy, hospital pharmacy, industry, and patient counselling — invoke them as slash-commands in your MCP client.

---

## Install in 30 seconds

```bash
# One line — every detected MCP client gets configured automatically.
pip install mcp-aemps && mcp-aemps install
```

No Python on the box? Three equivalent alternatives:

```bash
uvx mcp-aemps install                                                   # zero-install via uv (recommended)
docker run -p 8765:8765 ghcr.io/romanpert/mcp-aemps:latest              # multi-arch container
pipx run mcp-aemps install                                              # pipx
```

Restart your MCP client. The server shows up as `mcp-aemps`. Done.

> 💡 **No server to maintain.** By default, installers configure the client to spawn `uvx mcp-aemps@latest stdio` on demand — your agent boots the server when it needs it and shuts it down when it's done. For shared / multi-tenant deployments see [Deployment](#deployment).

---

## Compatibility — one command, 11 clients

| Client | Command | Notes |
|---|---|---|
| **Claude Desktop** | `mcp-aemps install claude-desktop` | Anthropic — stdio default, optional HTTP via `mcp-remote` |
| **Claude Code** | `mcp-aemps install claude-code` | Anthropic CLI — uses `claude mcp add` when available |
| **Codex CLI** | `mcp-aemps install codex` | OpenAI — `~/.codex/config.toml` |
| **Gemini CLI** | `mcp-aemps install gemini` | Google — `~/.gemini/settings.json`, native MCP (v0.4.17+) |
| **VS Code** | `mcp-aemps install vscode` | GitHub Copilot Chat MCP — dedicated `mcp.json` (post-2025) |
| **Cursor** | `mcp-aemps install cursor` | `~/.cursor/mcp.json` |
| **Windsurf** | `mcp-aemps install windsurf` | Codeium — `~/.codeium/windsurf/mcp_config.json` |
| **Zed** | `mcp-aemps install zed` | `context_servers` in `settings.json` |
| **Continue.dev** | `mcp-aemps install continue` | VS Code / JetBrains extension — YAML |
| **JetBrains Junie** | `mcp-aemps install jetbrains` | `~/.junie/mcp.json` |
| **Antigravity** | `mcp-aemps install antigravity` | Google — agentic IDE |

Installers are **idempotent** (re-run safely), **atomic** (write succeeds fully or not at all), **additive** (preserves your other entries), **port-aware** (read the actual port `mcp-aemps up` bound to), and **auto-purge legacy aliases** (`aemps-cima`, etc.) to clean up old installations. `mcp-aemps install` with no subcommand configures every detected client at once.

---

## Why mcp-aemps

**🏛️ Regulator-grade.** Every answer cites the officially documented CIMA REST endpoint + timestamp. Per-request audit trail via structured JSON logs (aligned with EU GMP Annex 11). No hallucination, no derived data — only the published AEMPS registry, exposed as-is.

**🔒 Read-only by construction.** Thin proxy over the public AEMPS API. Zero writes. Zero PII processed. Zero clinical decision support — this is **NOT a medical device** (MDR 2017/745 doesn't apply). Threat-model details in [SECURITY.md](SECURITY.md).

**🌐 Open standard.** Apache-2.0. Listed in [registry.modelcontextprotocol.io](https://registry.modelcontextprotocol.io). Reference implementation for MCP servers in regulated sectors — anyone wanting an official mirror of their own NCA (EMA, AIFA, Swissmedic, …) has the blueprint here.

---

## Catalog

<details>
<summary><strong>21 MCP tools</strong> — every tool maps 1:1 to an official CIMA REST endpoint</summary>

| Tool | CIMA Endpoint | Description |
|------|--------------|-------------|
| `obtener_medicamento` | `GET /medicamento` | Full drug record by CN or nregistro |
| `buscar_medicamentos` | `GET /medicamentos` | Filtered/paginated search (20+ filters) |
| `buscar_en_ficha_tecnica` | `POST /buscarEnFichaTecnica` | Full-text search inside SmPCs |
| `listar_presentaciones` | `GET /presentaciones` | Presentations list with filters |
| `obtener_presentacion` | `GET /presentacion/:cn` | Detail by National Code |
| `buscar_vmpp` | `GET /vmpp` | Clinical equivalents (VMP/VMPP) |
| `consultar_maestras` | `GET /maestras` | ATC, active ingredients, forms, labs |
| `registro_cambios` | `GET\|POST /registroCambios` | Authorization history |
| `problemas_suministro` | `GET /psuministro` + `GET /psuministro/v2/cn/:cn` | Supply problems — global or per CN |
| `problemas_suministro_dcp` | `GET /psuministro/v2/dcp/:dcp` | Supply problems by DCP |
| `problemas_suministro_dcpf` | `GET /psuministro/v2/dcpf/:dcpf` | Supply problems by DCPF (with form) |
| `listar_notas` / `obtener_notas` | `GET /notas/:nregistro` | Safety notes |
| `listar_materiales` / `obtener_materiales` | `GET /materiales/:nregistro` | Safety informational materials |
| `doc_secciones` | `GET /docSegmentado/secciones/:tipo` | Section metadata |
| `doc_contenido` | `GET /docSegmentado/contenido/:tipo` | Section content (JSON / HTML / plain) |
| `html_ficha_tecnica` | `GET /dochtml/ft/:nregistro/:file` | Full SmPC HTML |
| `html_prospecto` | `GET /dochtml/p/:nregistro/:file` | Full leaflet HTML |

All tools ship with [MCP annotations](https://blog.modelcontextprotocol.io/posts/2026-03-16-tool-annotations/) — `readOnlyHint: true`, `destructiveHint: false`, `idempotentHint: true`, `openWorldHint: true` — so spec-compliant clients don't ask for confirmation per query.

</details>

<details>
<summary><strong>11 curated resources</strong> under the <code>cima://</code> URI scheme — cacheable, no token cost</summary>

**Static resources:**

| URI | Content |
|---|---|
| `cima://maestras/atc` | Full ATC code tree |
| `cima://maestras/principios-activos` | Full active-ingredient listing |
| `cima://maestras/laboratorios` | Marketing-authorisation holders |
| `cima://maestras/formas-farmaceuticas` | Pharmaceutical forms |
| `cima://maestras/vias-administracion` | Administration routes |

**Templates:**

| URI template | Content |
|---|---|
| `cima://maestras/atc/{codigo}` | ATC lookup (e.g. C09AA02 → Enalapril) |
| `cima://maestras/principios-activos/{id}` | Active-ingredient lookup |
| `cima://docs/ficha-tecnica/{nregistro}` | Full SmPC HTML |
| `cima://docs/ficha-tecnica/{nregistro}/{seccion}` | Specific SmPC section (4.1, 4.8, 5.1, …) |
| `cima://docs/prospecto/{nregistro}` | Full leaflet HTML |
| `cima://docs/prospecto/{nregistro}/{seccion}` | Specific leaflet section (1, 2, 3, 4, 5, 6) |

</details>

<details>
<summary><strong>10 curated MCP prompts</strong> — professional and patient workflows ready to invoke</summary>

| Prompt | Audience | Use case |
|---|---|---|
| `identificar_cn` | Community pharmacy | One-screen summary card from a National Code |
| `equivalencias_genericas` | Community pharmacy | Substitution during a supply shortage |
| `vigilancia_paciente` | Hospital pharmacy | Active safety notes for a patient's medication portfolio |
| `comparar_fichas_tecnicas` | Hospital + industry | Wide-format SmPC comparison across 2-5 medicines |
| `auditar_cartera_laboratorio` | Industry | Full regulatory snapshot of a laboratory |
| `monitorizar_cambios_cartera` | Regulatory affairs | Diff of authorizations / withdrawals / modifications across a product list |
| `informe_posicionamiento_terapeutico` | Hospital + industry | IPE/IPT + authorised indication + mechanism |
| `material_visual_paciente` | Counselling | Photos, videos, audience-segregated informational material |
| `info_medicamento_para_no_sanitarios` | General public | Plain-language summary, no jargon |
| `comprobar_interaccion_principios_activos` | Hospital + industry | Textual search across SmPC §4.5 (Interactions) |

Patient-facing prompts always close with a "not medical advice" disclaimer — covered by test (`tests/test_prompts.py`); accidental removal breaks CI.

</details>

---

## Configuration

Zero required env vars — the server boots with sensible defaults. The most-used knobs:

| Variable | Default | What for |
|---|---|---|
| `UVICORN_HOST` | `127.0.0.1` | Loopback by default since v0.4.16. Use `mcp-aemps up --bind-all` or `UVICORN_HOST=0.0.0.0` for Docker / reverse-proxy. |
| `PORT` | `8765` | HTTP port. Auto-fallback if busy. |
| `REDIS_URL` | — | Enables distributed cache + shared rate-limit across replicas. Optional. |
| `MCP_AEMPS_LOCALE` | auto | `es` / `en`. Auto-detected from OS env. |
| `MCP_AEMPS_DNS_REBINDING_PROTECTION` | `true` | `Host` / `Origin` validation on `/mcp`. On by default since v0.4.16. Reverse-proxy: extend `MCP_AEMPS_ALLOWED_HOSTS`. |
| `METRICS_KEY` | — | **Required** to enable `/internal/metrics` (fail-closed since v0.4.16). |
| `OAUTH_ENABLED` | `false` | Enables OAuth 2.1 Resource-Server mode (multi-tenant SaaS). |
| `LOG_LEVEL` | `INFO` | Logging level |

OAuth 2.1: five env vars (`OAUTH_ISSUER`, `OAUTH_JWKS_URL`, `OAUTH_AUDIENCE`, `OAUTH_REQUIRED_SCOPES`). RFC 9728 Protected Resource Metadata exposed at `/.well-known/oauth-protected-resource`. No embedded Authorization Server — bring your own (Auth0 / Keycloak / Hydra / Stytch / Cloudflare). Details in [SECURITY.md](SECURITY.md).

---

## Deployment

**stdio (default).** Each MCP client spawns `uvx mcp-aemps@latest stdio` on demand. No server to maintain. No port management. Anthropic-canonical pattern — pick this if you only need your local agent to query CIMA.

**Shared HTTP (multi-user).** `mcp-aemps up --bind-all` + reverse-proxy (nginx / Caddy / Traefik) + `MCP_AEMPS_DNS_REBINDING_PROTECTION=true` + `MCP_AEMPS_ALLOWED_HOSTS=your-domain.com`. With OAuth 2.1 enabled for gating. One instance serves entire teams.

**Docker / Compose.**
```bash
docker run -p 8765:8765 ghcr.io/romanpert/mcp-aemps:latest
docker compose up -d   # with optional Redis for distributed cache
```

**MCP Registry.** Listed as `io.github.romanpert/mcp-aemps`. MCP-aware clients discover it automatically.

**Observability.** `/health/live`, `/health/ready` (Kubernetes-friendly), `/internal/metrics` (gated by `METRICS_KEY`). Structured JSON logs with correlation IDs. For Prometheus / OpenTelemetry, plug in via the factory's `extra_middleware` / `startup_hooks` extension points — see `app/factory.py`.

---

## Audit hooks (Claude Code)

[Claude Code's hook system](https://docs.anthropic.com/claude-code/hooks) runs client-side shell commands around every tool call. The matcher `mcp__mcp-aemps__*` captures every tool from this server — useful for GMP Annex 11 / EMA GVP audit trails.

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

Server-side equivalent available via `pre_tool_hooks` / `post_tool_hooks` in `create_app(...)` — useful when you can't trust every user to have the right `~/.claude/settings.json`. Details in `app/tool_hooks.py`.

---

## Compliance and security

mcp-aemps is built for regulated environments — without replacing professional judgement:

- **Public AEMPS data** — no PII, no patient data, no clinical decision support.
- **Audit trail** — structured JSON logs with correlation IDs, configurable retention (`LOG_RETENTION_DAYS`).
- **No GPL in the package** — clean Apache-2.0, distributable in private pharmaceutical stacks.
- **Threat model audited** — STRIDE pass end-to-end per release. Full policy in [SECURITY.md](SECURITY.md).
- **Coordinated disclosure** — `roman.p98@gmail.com`, triage in 48h.

Detailed posture (GDPR Art.5, LOPD-GDD, EU GMP Annex 11, EMA GVP Module VI): [CLAUDE.md](CLAUDE.md).

---

## Roadmap & versioning

mcp-aemps mirrors the CIMA REST surface 1:1 — no more, no less. Improvements through v1.0 are about **quality** (efficiency, security, scalability, modularity), not new features.

Add-ons that don't fit the scope rule (IPT PDF extraction, drug image downloads, multi-NCA aggregation, push notifications) live in a separate, premium-tier repo that imports `mcp-aemps>=0.4.x` from PyPI as a dependency.

Full CHANGELOG: [CHANGELOG.md](CHANGELOG.md). Versioning policy in [CLAUDE.md](CLAUDE.md).

---

## Contributing

Issues and PRs in English. Conventional commits. Setup, code standards, and the hard scope rules in [CONTRIBUTING.md](CONTRIBUTING.md).

> If you build something serious on mcp-aemps in pharmaceutical / hospital production, drop me a line — I'm interested in the use case, and roadmap items get prioritised partly by concrete demand.

---

## License & author

Apache-2.0 · Author: **Román Pérez Dumpert** · `roman.p98@gmail.com`

[![GitHub stars](https://img.shields.io/github/stars/romanpert/mcp-aemps?style=social)](https://github.com/romanpert/mcp-aemps/stargazers)

---

<sub>MCP Registry identifier: `mcp-name: io.github.romanpert/mcp-aemps`</sub>
