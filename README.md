<p align="center">
  <img src="https://raw.githubusercontent.com/romanpert/mcp-aemps/master/docs/mcp_aemps_logo_v2.jpg" alt="mcp-aemps" width="180"/>
</p>

<h1 align="center">mcp-aemps</h1>

<p align="center">
  <strong>El primer servidor MCP open-source y regulatorio-compliant para la industria farmacéutica.</strong><br/>
  Acceso en tiempo real al registro AEMPS/CIMA — más de 20.000 medicamentos autorizados en España, alertas de seguridad, problemas de suministro, fichas técnicas, prospectos — expuesto como herramientas MCP estructuradas para cualquier asistente de IA.
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
  <a href="https://pypi.org/project/mcp-aemps/"><img src="https://img.shields.io/pypi/dm/mcp-aemps?color=blue&label=PyPI%2Fmonth" alt="PyPI monthly"/></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-green" alt="License"/></a>
  <a href="https://github.com/romanpert/mcp-aemps/actions/workflows/ci.yml"><img src="https://github.com/romanpert/mcp-aemps/actions/workflows/ci.yml/badge.svg" alt="CI"/></a>
  <a href="https://registry.modelcontextprotocol.io/v0/servers?search=mcp-aemps"><img src="https://img.shields.io/badge/MCP%20Registry-listed-purple" alt="MCP Registry"/></a>
  <img src="https://img.shields.io/badge/CIMA%20API-v1.23-orange" alt="CIMA API v1.23"/>
</p>

---

## Qué hace

`mcp-aemps` envuelve la **API REST CIMA de la AEMPS** como un servidor MCP completo. Conecta Claude, GPT-4o, Gemini — o cualquier agente compatible con MCP — al registro oficial de medicamentos español. Consulta autorizaciones, fichas técnicas, notas de farmacovigilancia, problemas de suministro, equivalentes clínicos y más, en tiempo real.

**Fuente de datos:** [CIMA (AEMPS)](https://cima.aemps.es) — API pública, sin PII, sin autenticación requerida.
**Postura de compliance:** Proxy read-only. Audit trail por petición. Sin procesamiento de datos de pacientes.

---

## Instalación

```bash
# pip
pip install mcp-aemps

# zero-install (recomendado para clientes CLI)
uvx mcp-aemps up
pipx run mcp-aemps up

# Docker (multi-arch: linux/amd64, linux/arm64) — mínimo 0.1.6
docker run -p 8765:8765 ghcr.io/romanpert/mcp-aemps:latest

# Docker Compose
docker compose up -d
```

---

## Configuración del cliente en un solo comando

Tras `pip install mcp-aemps`, registra el servidor en tu cliente MCP con **un único comando** — sin editar JSON manualmente.

```bash
# Todos los clientes detectados a la vez
mcp-aemps install

# O elige uno
mcp-aemps install claude-desktop   # stdio por defecto (uvx auto-launch); HTTP via mcp-remote opcional
mcp-aemps install claude-code      # usa `claude mcp add` cuando está disponible
mcp-aemps install codex
mcp-aemps install vscode           # escribe mcp.servers en settings.json (Copilot Chat MCP)
mcp-aemps install cursor           # escribe ~/.cursor/mcp.json
mcp-aemps install windsurf         # escribe ~/.codeium/windsurf/mcp_config.json
mcp-aemps install zed              # escribe context_servers en Zed settings.json
mcp-aemps install continue         # escribe mcpServers en ~/.continue/config.yaml
mcp-aemps install jetbrains        # escribe ~/.junie/mcp.json (JetBrains Junie)

# URL o nombre de servidor personalizado
mcp-aemps install --url http://my-host:9000/mcp --name aemps
```

Para desinstalar:

```bash
mcp-aemps uninstall                  # quitar de todos
mcp-aemps uninstall claude-desktop   # solo un cliente
```

**Propiedades** — los instaladores son *idempotentes* (se pueden re-ejecutar con seguridad), *aditivos* (preservan tus otras entradas), *atómicos* (la escritura se completa entera o no se aplica) y *port-aware* (leen el puerto real al que se ha bindeado `mcp-aemps up`, así que puedes cambiar de puerto sin re-instalar).

**Rutas de configuración por SO:**

| Cliente | macOS | Windows | Linux |
|---|---|---|---|
| Claude Desktop | `~/Library/Application Support/Claude/claude_desktop_config.json` | `%APPDATA%\Claude\claude_desktop_config.json` | `~/.config/Claude/claude_desktop_config.json` |
| Claude Code | `claude mcp add` (preferido) → fallback `~/.claude.json` | igual | igual |
| Codex | `~/.codex/config.toml` | `%USERPROFILE%\.codex\config.toml` | `~/.codex/config.toml` |
| VS Code | `~/Library/Application Support/Code/User/settings.json` | `%APPDATA%\Code\User\settings.json` | `~/.config/Code/User/settings.json` |
| Cursor | `~/.cursor/mcp.json` | igual | igual |
| Windsurf | `~/.codeium/windsurf/mcp_config.json` | igual | igual |
| Zed | `~/.config/zed/settings.json` | `%APPDATA%\Zed\settings.json` | `~/.config/zed/settings.json` |
| Continue.dev | `~/.continue/config.yaml` | igual | igual |
| JetBrains Junie | `~/.junie/mcp.json` | igual | igual |

Tras instalar, **arranca el servidor** (puerto por defecto: **`8765`** — elegido para evitar colisiones con los típicos `8000`/`5000`/`3000`):

```bash
mcp-aemps up           # foreground
mcp-aemps up --daemon  # background
mcp-aemps up --port 9000  # puerto explícito; auto-fallback habilitado por defecto
```

Después reinicia tu cliente. `mcp-aemps` aparece como un servidor MCP disponible.

---

## Herramientas MCP — Endpoints oficiales CIMA

Todas las herramientas mapean 1:1 a endpoints REST CIMA oficialmente documentados.

| Herramienta | Endpoint CIMA | Descripción |
|------|--------------|-------------|
| `obtener_medicamento` | `GET /medicamento` | Ficha completa por CN o nregistro |
| `buscar_medicamentos` | `GET /medicamentos` | Búsqueda paginada con 20+ filtros |
| `buscar_en_ficha_tecnica` | `POST /buscarEnFichaTecnica` | Búsqueda full-text dentro de fichas técnicas |
| `listar_presentaciones` | `GET /presentaciones` | Listado de presentaciones con filtros |
| `obtener_presentacion` | `GET /presentacion/:cn` | Detalle de presentación por Código Nacional |
| `buscar_vmpp` | `GET /vmpp` | Equivalentes clínicos (VMP/VMPP) |
| `consultar_maestras` | `GET /maestras` | Catálogos maestros: ATC, principios activos, formas, laboratorios |
| `registro_cambios` | `GET\|POST /registroCambios` | Histórico de altas / bajas / modificaciones |
| `problemas_suministro` | `GET /psuministro` + `GET /psuministro/v2/cn/:cn` | Problemas de suministro — listado global o por Código Nacional |
| `problemas_suministro_dcp` | `GET /psuministro/v2/dcp/:dcp` | Problemas de suministro por DCP (descripción clínica) |
| `problemas_suministro_dcpf` | `GET /psuministro/v2/dcpf/:dcpf` | Problemas de suministro por DCPF (con forma farmacéutica) |
| `listar_notas` / `obtener_notas` | `GET /notas/:nregistro` | Notas de seguridad |
| `listar_materiales` / `obtener_materiales` | `GET /materiales/:nregistro` | Materiales informativos de seguridad |
| `doc_secciones` | `GET /docSegmentado/secciones/:tipo` | Metadatos de secciones de FT / prospecto |
| `doc_contenido` | `GET /docSegmentado/contenido/:tipo` | Contenido de sección (JSON / HTML / texto plano) |
| `html_ficha_tecnica` | `GET /dochtml/ft/:nregistro/:file` | HTML completo de la ficha técnica |
| `html_prospecto` | `GET /dochtml/p/:nregistro/:file` | HTML completo del prospecto |

Los problemas de suministro implementan **resolución dual-channel**: v2 por CN (enriquecida: estado de autorización, flag de comercialización) con fallback automático a v1 por compatibilidad.

---

## Ciclo de vida de los datos

- **Sin ficheros locales requeridos.** Todos los datos se obtienen de la API CIMA bajo demanda.
- **Cache Redis** (opcional): warm-up de catálogos maestros al arranque, refresco automático cada 24h sin reiniciar la aplicación.
- **Resolución CN → nregistro** vía `GET /presentacion/:cn` (siempre actual, sin datos locales obsoletos).
- Fallback elegante a cache en memoria cuando Redis no está disponible.

---

## Configuración

Todas las opciones se configuran vía variables de entorno:

| Variable | Default | Descripción |
|----------|---------|-------------|
| `PORT` | `8765` | Puerto del servidor (`mcp-aemps up --auto-port` busca uno libre si está ocupado) |
| `REDIS_URL` | — | Conexión a Redis o Valkey (opcional, habilita cache + rate-limit distribuidos) |
| `ALLOWED_ORIGINS` | `http://localhost:3000` | Orígenes CORS (no usar `*` en producción) |
| `METRICS_KEY` | — | Si se establece, `/internal/metrics` requiere la cabecera `X-Metrics-Key`. Recomendado en producción. |
| `LOG_LEVEL` | `INFO` | Nivel de logging |
| `LOG_RETENTION_DAYS` | `90` | Retención de logs rotados diariamente + gzipped |
| `MAX_RESULTS` | `30` | Máximo de items por página en endpoints de listado |
| `MCP_AEMPS_LOCALE` | auto | Idioma de strings LLM-facing: `es` o `en`. Auto-detectado de `$LANG`/`$LC_ALL` si no se establece (default `es`). |
| `OAUTH_ENABLED` | `false` | Activa modo OAuth 2.1 Resource-Server. Ver sección OAuth. |

---

## Observabilidad

Incluye **observabilidad in-process ligera** — sin requerir collector externo:

- **Liveness** en `/health/live` — proceso vivo (siempre 200 si el event loop responde).
- **Readiness** en `/health/ready` — backend de cache alcanzable Y warmup de maestras completado (devuelve 503 durante el arranque). Conectar a `readinessProbe` de Kubernetes.
- **Snapshot combinado** en `/health` — JSON `{status, version, cache}` (mantenido por compatibilidad).
- **Métricas in-process** en `/internal/metrics` — JSON `{requests_total, requests_by_path, status_codes, errors_5xx, uptime_seconds}`. Establece `METRICS_KEY` para requerir la cabecera `X-Metrics-Key`.
- **Logging estructurado stdlib** con rotación diaria + retención gzip.

Para tracing OpenTelemetry o exposición Prometheus, reemplaza el middleware de métricas vía los puntos de extensión `extra_middleware` / `startup_hooks` del factory (ver `app/factory.py`).

---

## Idioma (i18n)

Las strings LLM-facing (descripciones de tools, system prompt, descripciones y bodies de prompts) se entregan en **español (default)** e **inglés**. Cambia con la variable `MCP_AEMPS_LOCALE`:

```bash
# Default — auto-detectado del SO; sin variable → es
uvx mcp-aemps stdio

# Inglés explícito (siempre gana sobre el sniff del SO)
MCP_AEMPS_LOCALE=en uvx mcp-aemps stdio
```

**Auto-detección del idioma del sistema operativo** (`$LC_ALL` / `$LANG` / `$LANGUAGE`): sistemas en inglés reciben `en`, todo lo demás (incluyendo locale POSIX `C` y locales no reconocidos) cae a `es` porque la fuente de datos CIMA es española. Una `MCP_AEMPS_LOCALE` explícita siempre gana sobre la auto-detección.

Desde v0.2.9 el catálogo **completo** de prompts (descripciones + bodies + disclaimer dirigido a pacientes) se entrega en ambos idiomas. Ambos locales registran los mismos 10 nombres de prompt con las mismas signaturas — los clientes que hardcodean nombres siguen funcionando al cambiar de idioma.

---

## OAuth 2.1 (opt-in)

mcp-aemps es **público por defecto** porque CIMA es público. Para despliegues SaaS multi-tenant o cualquier setup donde necesites gating de acceso, el servidor se puede activar en modo **OAuth 2.1 Resource-Server** con cinco variables de entorno:

```bash
export OAUTH_ENABLED=true
export OAUTH_ISSUER=https://auth.example.com
export OAUTH_JWKS_URL=https://auth.example.com/.well-known/jwks.json
export OAUTH_AUDIENCE=https://mcp-aemps.example.com/mcp
export OAUTH_REQUIRED_SCOPES=mcp:read
```

Cuando está habilitado:

* Cada llamada a tool MCP sobre HTTP en `/mcp` requiere un JWT Bearer válido firmado por el Authorization Server configurado.
* El documento PRM se publica en `/.well-known/oauth-protected-resource` (RFC 9728), de modo que cualquier cliente MCP spec-compliant puede descubrir el AS vía Dynamic Client Registration (RFC 7591).
* stdio no se ve afectado — el acceso process-local se controla por permisos de SO, no por OAuth.

**Sin Authorization Server embebido.** Apunta `OAUTH_ISSUER` a cualquier IdP existente — Auth0, Stytch, Cloudflare Workers OAuth Provider, Hydra, Keycloak, etc. mcp-aemps es stateless: verifica tokens, nunca los emite.

Validado end-to-end en v0.2.10: POST `/mcp` sin token devuelve 401 con cabecera `WWW-Authenticate: Bearer error="invalid_token", resource_metadata="<URL del PRM>"` (RFC 6750 §3 + RFC 9728).

---

## Anotaciones de Tools

Cada herramienta CIMA se entrega con las [anotaciones MCP](https://blog.modelcontextprotocol.io/posts/2026-03-16-tool-annotations/) que los clientes spec-compliant (Claude Desktop, ChatGPT Dev Mode, Cursor, Continue, Zed, JetBrains Junie, …) usan para su UI de auto-aprobación:

| Hint              | Valor | Razón                                                       |
|-------------------|-------|-------------------------------------------------------------|
| `readOnlyHint`    | true  | El servidor es un proxy fino — no hay escrituras upstream.  |
| `destructiveHint` | false | Sin mutaciones del entorno, nunca.                          |
| `idempotentHint`  | true  | Mismos args en el mismo instante → mismo payload.           |
| `openWorldHint`   | true  | Las tools golpean la API HTTP externa de CIMA.              |

Esto hace que los clientes que respetan la spec no pidan confirmación en cada query CIMA — solo gatean llamadas donde las anotaciones lo justifican. Para Claude Code en concreto, ver más abajo cómo construir tus propias confirmation gates independientemente de las anotaciones.

---

## Recursos MCP curados

mcp-aemps expone **5 recursos estáticos + 6 templates** bajo el esquema URI `cima://`. Los recursos son URIs read-only que los clientes MCP pueden **streamear** y **cachear** sin pagar el coste en tokens de una llamada a tool — la fuente dominante de gasto de tokens en sesiones interactivas.

### Recursos estáticos (auto-descubribles vía `resources/list`)

| URI | MIME | Contenido |
|---|---|---|
| `cima://maestras/atc` | `application/json` | Árbol completo de códigos ATC |
| `cima://maestras/principios-activos` | `application/json` | Listado completo de principios activos |
| `cima://maestras/laboratorios` | `application/json` | Laboratorios titulares de autorización AEMPS |
| `cima://maestras/formas-farmaceuticas` | `application/json` | Formas farmacéuticas (comprimido, inyectable, …) |
| `cima://maestras/vias-administracion` | `application/json` | Vías de administración (oral, IV, tópica, …) |

### Templates (`resources/templates/list`)

| URI template | Contenido |
|---|---|
| `cima://maestras/atc/{codigo}` | Lookup ATC por código (p.ej. C09AA02 → Enalapril) |
| `cima://maestras/principios-activos/{id}` | Lookup principio activo por id AEMPS |
| `cima://docs/ficha-tecnica/{nregistro}` | HTML completo de la ficha técnica |
| `cima://docs/ficha-tecnica/{nregistro}/{seccion}` | Sección concreta de la FT (4.1, 4.8, 5.1, …) |
| `cima://docs/prospecto/{nregistro}` | HTML completo del prospecto |
| `cima://docs/prospecto/{nregistro}/{seccion}` | Sección concreta del prospecto (1, 2, 3, 4, 5, 6) |

Disponibles en **ambos transportes** (stdio y `/mcp` HTTP) — desde v0.2.7 existe un único `FastMCP` server que sirve tools, prompts y resources para los dos lados.

---

## Prompts MCP curados

mcp-aemps entrega **10 [Prompts MCP](https://modelcontextprotocol.io/specification/server/prompts)** curados — plantillas de workflow definidas en el servidor que invocas explícitamente desde tu cliente MCP (Claude Desktop, Continue, Cursor, Zed, …). Orquestan las llamadas correctas a tools CIMA para los workflows profesionales y de paciente más comunes, así no tienes que recordar qué tools encadenar.

> **Disponibilidad en transportes**: los prompts se entregan en **ambos** transportes — stdio (`uvx mcp-aemps stdio`) y Streamable HTTP en `/mcp`. Desde v0.2.7 el transporte HTTP usa la app Streamable-HTTP nativa de FastMCP (sin indirección de fastapi-mcp), de modo que tools, prompts, resources y annotations se sirven todos desde la misma instancia FastMCP.

### Catálogo

| Prompt | Args | Caso de uso |
|---|---|---|
| **`identificar_cn`** | `cn` | **Farmacia comunitaria** — el paciente trae una caja con un Código Nacional; tarjeta resumen one-screen con autorización, comercialización, receta, alertas activas, suministro, fotos oficiales y enlaces a documentación AEMPS. |
| **`equivalencias_genericas`** | `nregistro`, `comercializados_solo?` | **Farmacia comunitaria** — sustitución durante un desabastecimiento. Mismo principio activo + dosis + forma farmacéutica, con foto de la caja para confirmar visualmente. |
| **`vigilancia_paciente`** | `nregistros[]` | **Farmacia hospitalaria** — revisión de notas de seguridad activas para la cartera de medicación de un paciente. Alineado con EMA GVP Module VI. |
| **`comparar_fichas_tecnicas`** | `nregistros[]`, `secciones?` | **Hospital + industria** — tabla wide-format comparando 2-5 medicamentos sección a sección de la FT (4.1, 4.2, 4.3, 4.4, 4.5, 4.8 por defecto). |
| **`auditar_cartera_laboratorio`** | `laboratorio`, `incluir_no_comercializados?` | **Industria** — snapshot regulatorio completo de un laboratorio: métricas globales, áreas terapéuticas (ATC), triángulo negro, top con notas activas, riesgos de suministro, presencia de IPT. |
| **`monitorizar_cambios_cartera`** | `nregistros[]`, `desde_fecha?` | **Industria · regulatory affairs** — detecta cambios (alta, baja, modificación de FT/prospecto/comercialización/notas) sobre una lista de productos en un periodo. |
| **`informe_posicionamiento_terapeutico`** | `nregistro` | **Hospital + industria** — recupera el Informe Público de Evaluación (IPE/IPT) de AEMPS junto con la indicación autorizada (FT 4.1) y el mecanismo de acción (FT 5.1). Marca explícitamente cuando AEMPS no ha publicado IPT. |
| **`material_visual_paciente`** | `nregistro` | **Counseling al paciente** — fotos de la caja y de la pastilla, vídeos de uso (inhaladores, plumas de insulina, autoinyectores), material informativo segregado por audiencia. Cierra con disclaimer. |
| **`info_medicamento_para_no_sanitarios`** | `nombre_o_cn` | **Público general** — resumen llano sin jerga: qué es, para qué se usa, cómo es (fotos), alertas activas, dónde leer más. Cierra con disclaimer obligatorio "no es consejo médico". |
| **`comprobar_interaccion_principios_activos`** | `principios_activos[]` | **Farmacia hospitalaria + industria** — comprueba si la sección 4.5 (Interacciones) de las fichas técnicas AEMPS menciona interacciones cruzadas entre 2-5 principios activos. Búsqueda textual sobre documentación oficial; **NO sustituye una herramienta clínica formal** (BOT PLUS, Lexicomp, Stockley, Micromedex). |

### Cómo se invoca

En Claude Desktop (cuando el cliente lo soporta), aparecen como slash-commands `/mcp__mcp-aemps__<nombre>` en el menú de prompts, o se pueden listar via `prompts/list` desde cualquier cliente MCP-compliant.

Ejemplo programático con el SDK MCP de Python:

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
        # result.messages[0].content.text → el cuerpo del prompt listo para enviar al LLM
```

### Diseño

Cada prompt instruye al LLM **qué herramientas llamar, en qué orden y cómo formatear la salida**. Aprovechan la riqueza del payload de `obtener_medicamento` (que incluye `docs[]` con Ficha Técnica, Prospecto, Informe Público de Evaluación y Plan de Gestión de Riesgos; `fotos[]` con la caja y la forma farmacéutica; el flag `materialesInf` para vídeos vía `obtener_materiales`) en lugar de tratar CIMA como un simple lookup de campos.

Los prompts **dirigidos a pacientes** (`material_visual_paciente`, `info_medicamento_para_no_sanitarios`, `comprobar_interaccion_principios_activos`) cierran siempre con un disclaimer explícito "no es consejo médico — consulte a su médico o farmacéutico". Está cubierto por test (`tests/test_prompts.py`); su eliminación accidental rompe CI.

---

## Integración con Claude Code hooks

El [sistema de hooks de Claude Code](https://docs.anthropic.com/claude-code/hooks) ejecuta comandos shell client-side alrededor de cada invocación de tool, incluyendo llamadas a servidores MCP como mcp-aemps. El matcher `mcp__mcp-aemps__*` captura cada herramienta expuesta por este servidor. Dos recetas concretas para añadir a `~/.claude/settings.json`:

### 1 · Auditar cada llamada mcp-aemps a un log JSONL

Útil para audit trails GMP Annex 11 / EMA GVP — registro completo de qué tool se invocó con qué argumentos, cuándo, en qué sesión.

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

El hook recibe la llamada de tool como JSON por stdin; `jq` la aplana a una línea por llamada. Rota `~/.claude/audit/` con `logrotate` o tu agente SIEM.

### 2 · Enviar latencia por tool a un SIEM

Empareja `PreToolUse` (start del timer) con `PostToolUse` (stop del timer) y haz POST del delta más el nombre de tool a tu endpoint de ingest del SIEM.

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

> **Equivalente server-side.** mcp-aemps también expone `pre_tool_hooks` / `post_tool_hooks` en `create_app(...)` de modo que el mismo audit trail puede emitirse server-side independientemente del cliente MCP que se conecte (útil para despliegues compartidos donde no puedes confiar en que cada usuario tenga el `~/.claude/settings.json` correcto). Ver `app/tool_hooks.py`.

---

## Seguridad

- Usuario Docker non-root (UID 10001)
- Cabeceras de seguridad: `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`
- `pyjwt[crypto]` — sin `python-jose` (CVE-2024-33663)
- Sin secretos en repo — toda configuración via env vars
- CORS configurable, no `*` en producción

---

## Documentación de referencia

Documentos AEMPS oficiales en [`docs/`](docs/):

- [`CIMA_REST_API.pdf`](docs/CIMA_REST_API.pdf) — CIMA REST API v1.23
- [`CIMA-problemas-suministro.pdf`](docs/CIMA-problemas-suministro.pdf) — API de Problemas de Suministro (AEMPS / Ministerio de Sanidad)

---

## Licencia

Apache-2.0 © [Román Pérez Dumpert](https://github.com/romanpert)

<!-- MCP Registry ownership marker — DO NOT REMOVE -->
<sub><sup>mcp-name: io.github.romanpert/mcp-aemps</sup></sub>
