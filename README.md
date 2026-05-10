<p align="center">
  <img src="https://raw.githubusercontent.com/romanpert/mcp-aemps/master/docs/mcp_aemps_logo_v2.jpg" alt="mcp-aemps" width="180"/>
</p>

<h1 align="center">mcp-aemps</h1>

<!-- mcp-name: io.github.romanpert/mcp-aemps -->

<p align="center">
  <strong>Datos farmacéuticos oficiales, listos para tu agente.</strong><br/>
  El primer servidor MCP open-source para la industria farmacéutica. <strong>20.000+ medicamentos AEMPS</strong>, en tiempo real, regulator-grade.
</p>

<p align="center">
  🇪🇸 <strong>Español</strong> · <a href="README.en.md">🇬🇧 English</a>
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

---

## Lo que tu agente puede hacer

Conecta tu asistente — Claude, ChatGPT, Gemini, Cursor, Continue, Zed, Junie — al registro oficial AEMPS / CIMA. Sin scrapers. Sin hardcoded snapshots. Sin patient data. Cada respuesta cita endpoint REST oficial y fecha de consulta.

> **Tú:** «¿Qué efectos adversos graves aparecen en la ficha técnica de **HUMIRA 40 mg**?»
> **Tu agente** consulta `obtener_medicamento` → `doc_contenido` (sección 4.8 de la FT) → devuelve estructurado, con timestamp y fuente AEMPS.

> **Tú:** «Lista los problemas de suministro vigentes para **omeprazol 20 mg cápsulas**.»
> **Tu agente** llama `problemas_suministro_dcpf` → devuelve los lotes afectados, fechas previstas de retorno y alternativas terapéuticas equivalentes.

> **Tú:** «¿Qué notas de farmacovigilancia ha publicado AEMPS sobre **inhibidores SGLT2** en los últimos 6 meses?»
> **Tu agente** filtra `listar_notas` + recupera `obtener_notas` → resumen accionable con enlaces oficiales.

> **Tú:** «Dame un equivalente clínico (mismo VMP) para **simvastatina 20 mg comprimidos** sin lactosa.»
> **Tu agente** cruza `buscar_vmpp` + `buscar_en_ficha_tecnica("lactosa")` → propone alternativas con autorización AEMPS vigente y excipientes confirmados.

> **Tú:** «¿Qué cambia entre la FT actual de **Eliquis** y la versión publicada hace 90 días?»
> **Tu agente** invoca el prompt curado `monitorizar_cambios_cartera` → diff por sección sobre la documentación oficial.

10 prompts curados más, cubriendo farmacia comunitaria, hospitalaria, industria y counseling al paciente — listos para invocar como slash-commands en tu cliente MCP.

---

## Instalación en 30 segundos

```bash
# Una línea — cualquier cliente MCP detectado se configura automáticamente.
pip install mcp-aemps && mcp-aemps install
```

¿Sin Python en la máquina? Hay tres alternativas equivalentes:

```bash
uvx mcp-aemps install                                                   # zero-install vía uv (recomendado)
docker run -p 8765:8765 ghcr.io/romanpert/mcp-aemps:latest              # contenedor multi-arch
pipx run mcp-aemps install                                              # pipx
```

Reinicia tu cliente MCP. El servidor aparece como `mcp-aemps`. Listo.

> 💡 **Sin servidor que mantener.** Por defecto los instaladores configuran el cliente para lanzar `uvx mcp-aemps@latest stdio` bajo demanda — el agente arranca el servidor cuando lo necesita y lo apaga cuando termina. Para despliegues compartidos / multi-tenant ver [Despliegue](#despliegue).

---

## Compatibilidad — un comando, 11 clientes

| Cliente | Comando | Notas |
|---|---|---|
| **Claude Desktop** | `mcp-aemps install claude-desktop` | Anthropic — stdio por defecto, HTTP via `mcp-remote` opcional |
| **Claude Code** | `mcp-aemps install claude-code` | Anthropic CLI — usa `claude mcp add` cuando está disponible |
| **Codex CLI** | `mcp-aemps install codex` | OpenAI — `~/.codex/config.toml` |
| **Gemini CLI** | `mcp-aemps install gemini` | Google — `~/.gemini/settings.json`, MCP nativo (v0.4.17+) |
| **VS Code** | `mcp-aemps install vscode` | GitHub Copilot Chat MCP — `mcp.json` dedicado (post-2025) |
| **Cursor** | `mcp-aemps install cursor` | `~/.cursor/mcp.json` |
| **Windsurf** | `mcp-aemps install windsurf` | Codeium — `~/.codeium/windsurf/mcp_config.json` |
| **Zed** | `mcp-aemps install zed` | `context_servers` en `settings.json` |
| **Continue.dev** | `mcp-aemps install continue` | Extensión VS Code / JetBrains — YAML |
| **JetBrains Junie** | `mcp-aemps install jetbrains` | `~/.junie/mcp.json` |
| **Antigravity** | `mcp-aemps install antigravity` | Google — IDE agente |

Los instaladores son **idempotentes** (re-ejecuta sin miedo), **atómicos** (la escritura se completa entera o no se aplica), **additive** (preservan tus otras entradas), **port-aware** (leen el puerto real bound por `mcp-aemps up`), y **purgan automáticamente aliases legacy** (`aemps-cima`, etc.) para limpiar instalaciones de versiones antiguas. `mcp-aemps install` (sin subcomando) configura todos los detectados a la vez.

---

## Por qué mcp-aemps

**🏛️ Regulator-grade.** Cada respuesta cita endpoint CIMA REST oficialmente documentado + timestamp. Audit trail por petición vía logs JSON estructurados (alineado con EU GMP Annex 11). Sin alucinación, sin datos derivados — solo el registro AEMPS publicado, expuesto tal cual.

**🔒 Read-only por construcción.** Proxy fino sobre la API pública AEMPS. Cero escrituras. Cero PII procesada. Cero clinical decision support — esto **NO es un dispositivo médico** (MDR 2017/745 no aplica). Detalles del threat model en [SECURITY.md](SECURITY.md).

**🌐 Estándar abierto.** Apache-2.0. Listado en [registry.modelcontextprotocol.io](https://registry.modelcontextprotocol.io). Implementación de referencia para servidores MCP en sectores regulados — quien quiera mirror oficial de su propio NCA (EMA, AIFA, Swissmedic, …) tiene aquí el blueprint.

---

## Catálogo

<details>
<summary><strong>21 herramientas MCP</strong> — todas mapean 1:1 a endpoints CIMA REST oficiales</summary>

| Herramienta | Endpoint CIMA | Descripción |
|------|--------------|-------------|
| `obtener_medicamento` | `GET /medicamento` | Ficha completa por CN o nregistro |
| `buscar_medicamentos` | `GET /medicamentos` | Búsqueda paginada con 20+ filtros |
| `buscar_en_ficha_tecnica` | `POST /buscarEnFichaTecnica` | Full-text dentro de fichas técnicas |
| `listar_presentaciones` | `GET /presentaciones` | Listado con filtros |
| `obtener_presentacion` | `GET /presentacion/:cn` | Detalle por Código Nacional |
| `buscar_vmpp` | `GET /vmpp` | Equivalentes clínicos (VMP/VMPP) |
| `consultar_maestras` | `GET /maestras` | ATC, principios activos, formas, laboratorios |
| `registro_cambios` | `GET\|POST /registroCambios` | Histórico de altas / bajas / modificaciones |
| `problemas_suministro` | `GET /psuministro` + `GET /psuministro/v2/cn/:cn` | Listado global o por Código Nacional |
| `problemas_suministro_dcp` | `GET /psuministro/v2/dcp/:dcp` | Por DCP (descripción clínica) |
| `problemas_suministro_dcpf` | `GET /psuministro/v2/dcpf/:dcpf` | Por DCPF (con forma farmacéutica) |
| `listar_notas` / `obtener_notas` | `GET /notas/:nregistro` | Notas de seguridad |
| `listar_materiales` / `obtener_materiales` | `GET /materiales/:nregistro` | Materiales informativos |
| `doc_secciones` | `GET /docSegmentado/secciones/:tipo` | Metadatos de secciones |
| `doc_contenido` | `GET /docSegmentado/contenido/:tipo` | Contenido (JSON / HTML / texto) |
| `html_ficha_tecnica` | `GET /dochtml/ft/:nregistro/:file` | HTML completo de la FT |
| `html_prospecto` | `GET /dochtml/p/:nregistro/:file` | HTML completo del prospecto |

Todas las tools llevan [anotaciones MCP](https://blog.modelcontextprotocol.io/posts/2026-03-16-tool-annotations/) — `readOnlyHint: true`, `destructiveHint: false`, `idempotentHint: true`, `openWorldHint: true` — para que clientes spec-compliant no pidan confirmación por consulta.

</details>

<details>
<summary><strong>11 recursos curados</strong> bajo el esquema URI <code>cima://</code> — cacheables, sin coste de tokens</summary>

**Recursos estáticos:**

| URI | Contenido |
|---|---|
| `cima://maestras/atc` | Árbol completo de códigos ATC |
| `cima://maestras/principios-activos` | Listado completo |
| `cima://maestras/laboratorios` | Laboratorios titulares de autorización |
| `cima://maestras/formas-farmaceuticas` | Comprimido, inyectable, … |
| `cima://maestras/vias-administracion` | Oral, IV, tópica, … |

**Templates:**

| URI template | Contenido |
|---|---|
| `cima://maestras/atc/{codigo}` | Lookup ATC (p.ej. C09AA02 → Enalapril) |
| `cima://maestras/principios-activos/{id}` | Lookup principio activo |
| `cima://docs/ficha-tecnica/{nregistro}` | HTML completo |
| `cima://docs/ficha-tecnica/{nregistro}/{seccion}` | Sección concreta (4.1, 4.8, 5.1, …) |
| `cima://docs/prospecto/{nregistro}` | HTML completo |
| `cima://docs/prospecto/{nregistro}/{seccion}` | Sección concreta (1, 2, 3, 4, 5, 6) |

</details>

<details>
<summary><strong>10 prompts MCP curados</strong> — workflows profesionales y de paciente listos para invocar</summary>

| Prompt | Audiencia | Caso de uso |
|---|---|---|
| `identificar_cn` | Farmacia comunitaria | Tarjeta resumen one-screen a partir de un Código Nacional |
| `equivalencias_genericas` | Farmacia comunitaria | Sustitución durante desabastecimiento |
| `vigilancia_paciente` | Farmacia hospitalaria | Notas de seguridad activas para una cartera de medicación |
| `comparar_fichas_tecnicas` | Hospital + industria | Tabla wide-format comparando 2-5 medicamentos sección a sección |
| `auditar_cartera_laboratorio` | Industria | Snapshot regulatorio completo de un laboratorio |
| `monitorizar_cambios_cartera` | Regulatory affairs | Diff de altas / bajas / modificaciones sobre una lista de productos |
| `informe_posicionamiento_terapeutico` | Hospital + industria | IPE/IPT + indicación autorizada + mecanismo |
| `material_visual_paciente` | Counseling | Fotos, vídeos, material informativo segregado por audiencia |
| `info_medicamento_para_no_sanitarios` | Público general | Resumen llano sin jerga |
| `comprobar_interaccion_principios_activos` | Hospital + industria | Búsqueda textual sobre la sección 4.5 (Interacciones) |

Los prompts dirigidos a pacientes cierran siempre con un disclaimer "no es consejo médico" — cubierto por test (`tests/test_prompts.py`); su eliminación rompe CI.

</details>

---

## Configuración

Cero variables requeridas — el servidor arranca con defaults sensatos. Las opciones más usadas:

| Variable | Default | Para qué |
|---|---|---|
| `UVICORN_HOST` | `127.0.0.1` | Loopback por defecto desde v0.4.16. `mcp-aemps up --bind-all` o `UVICORN_HOST=0.0.0.0` para Docker / reverse-proxy. |
| `PORT` | `8765` | Puerto HTTP. Auto-fallback si está ocupado. |
| `REDIS_URL` | — | Activa cache distribuida + rate-limit compartido entre réplicas. Opcional. |
| `MCP_AEMPS_LOCALE` | auto | `es` / `en`. Auto-detecta del SO. |
| `MCP_AEMPS_DNS_REBINDING_PROTECTION` | `true` | Validación `Host` / `Origin` en `/mcp`. Activado por defecto desde v0.4.16. Reverse-proxy: extiende `MCP_AEMPS_ALLOWED_HOSTS`. |
| `METRICS_KEY` | — | **Requerido** para habilitar `/internal/metrics` (fail-closed desde v0.4.16). |
| `OAUTH_ENABLED` | `false` | Activa modo OAuth 2.1 Resource-Server (multi-tenant SaaS). |
| `LOG_LEVEL` | `INFO` | Nivel logging |

OAuth 2.1: cinco env vars (`OAUTH_ISSUER`, `OAUTH_JWKS_URL`, `OAUTH_AUDIENCE`, `OAUTH_REQUIRED_SCOPES`). RFC 9728 Protected Resource Metadata expuesto en `/.well-known/oauth-protected-resource`. Sin Authorization Server embebido — bring your own (Auth0 / Keycloak / Hydra / Stytch / Cloudflare). Detalles en [SECURITY.md](SECURITY.md).

---

## Despliegue

**stdio (default).** Cada cliente MCP arranca `uvx mcp-aemps@latest stdio` bajo demanda. Sin servidor que mantener. Sin gestión de puertos. Es el patrón Anthropic-canonical — usa esto si solo quieres que tu agente local consulte CIMA.

**HTTP compartido (multi-usuario).** `mcp-aemps up --bind-all` + reverse-proxy (nginx / Caddy / Traefik) + `MCP_AEMPS_DNS_REBINDING_PROTECTION=true` + `MCP_AEMPS_ALLOWED_HOSTS=tu-dominio.com`. Con OAuth 2.1 activado para gating. Una sola instancia sirve a equipos enteros.

**Docker / Compose.**
```bash
docker run -p 8765:8765 ghcr.io/romanpert/mcp-aemps:latest
docker compose up -d   # con Redis opcional para cache distribuida
```

**MCP Registry.** Listado como `io.github.romanpert/mcp-aemps`. Los clientes MCP-aware lo descubren automáticamente.

**Observabilidad.** `/health/live`, `/health/ready` (Kubernetes-friendly), `/internal/metrics` (gated por `METRICS_KEY`). Logs JSON estructurados con correlation IDs. Para Prometheus / OpenTelemetry, plug-in vía `extra_middleware` / `startup_hooks` del factory — ver `app/factory.py`.

---

## Hooks de auditoría (Claude Code)

El [sistema de hooks de Claude Code](https://docs.anthropic.com/claude-code/hooks) ejecuta comandos shell client-side alrededor de cada llamada a tool. El matcher `mcp__mcp-aemps__*` captura cada herramienta de este servidor — útil para audit trails GMP Annex 11 / EMA GVP.

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

Equivalente server-side disponible vía `pre_tool_hooks` / `post_tool_hooks` en `create_app(...)` — útil cuando no puedes confiar en que cada usuario tenga el `~/.claude/settings.json` correcto. Detalles en `app/tool_hooks.py`.

---

## Compliance y seguridad

mcp-aemps está construido para entornos regulados — sin sustituir el juicio profesional:

- **Datos públicos AEMPS** — sin PII, sin patient data, sin clinical decision support.
- **Audit trail** — logs JSON estructurados con correlation IDs, retención configurable (`LOG_RETENTION_DAYS`).
- **Sin GPL en el paquete** — Apache-2.0 limpio, distribuible en stack farmacéutico privado.
- **Threat model auditado** — STRIDE pass end-to-end por release. Política completa en [SECURITY.md](SECURITY.md).
- **Disclosure coordinada** — `roman.p98@gmail.com`, triage en 48h.

Posture detallada (GDPR Art.5, LOPD-GDD, EU GMP Annex 11, EMA GVP Module VI): [CLAUDE.md](CLAUDE.md).

---

## Roadmap & versioning

mcp-aemps mirrorea el surface CIMA REST 1:1 — ni más, ni menos. Las mejoras hasta v1.0 son **calidad** (eficiencia, seguridad, escalabilidad, modularidad), no nuevas features.

Add-ons que NO encajan en esta scope rule (extracción de PDF de IPT, descarga de imágenes de medicamentos, agregación multi-NCA, push notifications) viven en un repo separado, premium-tier, que importa este `mcp-aemps>=0.4.x` desde PyPI como dependencia.

CHANGELOG completo: [CHANGELOG.md](CHANGELOG.md). Política de versionado en [CLAUDE.md](CLAUDE.md).

---

## Contribuir

Issues y PRs en inglés. Conventional commits. Setup, estándares de código, y las hard scope rules en [CONTRIBUTING.md](CONTRIBUTING.md).

> Si construyes algo serio sobre mcp-aemps en producción farmacéutica / hospitalaria, escríbeme — me interesa el use case, y los road-map items se priorizan en parte por demanda concreta.

---

## Licencia & autor

Apache-2.0 · Author: **Román Pérez Dumpert** · `roman.p98@gmail.com`

[![GitHub stars](https://img.shields.io/github/stars/romanpert/mcp-aemps?style=social)](https://github.com/romanpert/mcp-aemps/stargazers)

---

<sub>MCP Registry identifier: `mcp-name: io.github.romanpert/mcp-aemps`</sub>
