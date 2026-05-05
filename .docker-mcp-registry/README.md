# Docker MCP Registry submission — artefactos preparados

Esta carpeta contiene los artefactos listos para someter `mcp-aemps` al
[Docker MCP Registry oficial](https://github.com/docker/mcp-registry).

## Por qué estos archivos

Docker MCP Registry **rebuilda la imagen** desde nuestro `Dockerfile` y la
hostea en `mcp/mcp-aemps` en Docker Hub con firmas, SBOM y provenance —
no usan nuestra imagen GHCR (esa queda como mirror).

Su CI hace `task build -- --tools mcp-aemps` que arranca el contenedor y
le pide la lista de tools por el protocolo MCP stdio. Como nuestro server
es HTTP, Docker recomienda incluir un `tools.json` para evitar ese check
y aceptar la lista declarada — esto es lo que ya hemos generado.

## Archivos

| Archivo | Para qué sirve |
|---|---|
| `server.yaml` | Manifest oficial requerido por el registry |
| `tools.json` | Listado de las 21 tools MCP (saltea el `task build --tools` check) |

## Pasos para someterlo (manual, lo haces tú)

### 1. Fork del registry

Forkea **https://github.com/docker/mcp-registry** a tu GitHub. Clónalo:

```bash
git clone https://github.com/romanpert/mcp-registry.git
cd mcp-registry
git checkout -b add-mcp-aemps
```

### 2. Copiar nuestros artefactos

```bash
mkdir -p servers/mcp-aemps
cp ../mcp-aemps/.docker-mcp-registry/server.yaml servers/mcp-aemps/server.yaml
cp ../mcp-aemps/.docker-mcp-registry/tools.json servers/mcp-aemps/tools.json
```

### 3. Validar localmente (necesita Go + Task instalados)

```bash
# Instala Task una sola vez:  https://taskfile.dev/installation/
# Validación (no construye, solo lee tools.json gracias a su presencia):
task build -- --tools mcp-aemps
task catalog -- mcp-aemps
docker mcp catalog import "$PWD/catalogs/mcp-aemps/catalog.yaml"
```

Esto te enseña la entrada en Docker Desktop → MCP Toolkit. Verifica que
sale el icono, descripción y categoría healthcare.

```bash
# Limpieza tras validar:
docker mcp catalog reset
```

### 4. Commit + PR

```bash
git add servers/mcp-aemps/
git commit -m "Add mcp-aemps — Spanish AEMPS CIMA pharmaceutical registry"
git push -u origin add-mcp-aemps
```

Abre PR en https://github.com/docker/mcp-registry/compare. El equipo
Docker revisa típicamente en 1-3 días. Pueden pedir cambios menores
(descripción, categoría). Aprobado → tu MCP aparece en
**https://hub.docker.com/u/mcp** y en Docker Desktop → MCP Toolkit.

### 5. Tras aprobación

- La imagen `mcp/mcp-aemps:latest` queda disponible en Docker Hub
- Docker la rebuilda automáticamente cuando publicas un nuevo tag
  `vX.Y.Z` en nuestro repo (configuran webhooks)
- Tu README puede añadir el badge:
  ```markdown
  [![Docker MCP](https://img.shields.io/badge/Docker%20MCP-listed-blue)](https://hub.docker.com/r/mcp/mcp-aemps)
  ```

## Notas

- Esta carpeta (`.docker-mcp-registry/`) es local: NO se publica al
  registry, sólo es el "staging area" del que copias a tu fork
- Si actualizas el Dockerfile, server.yaml debería actualizar el SHA del
  commit en `source.commit` y abrirse un nuevo PR al registry

## Automatización (futuras releases)

El workflow `.github/workflows/docker-mcp-registry.yml` automatiza este
proceso para versiones nuevas: cuando empujes un tag `vX.Y.Z`, abre/actualiza
automáticamente un PR `bump-mcp-aemps-X.Y.Z` contra `docker/mcp-registry`
desde tu fork `romanpert/mcp-registry`.

Para activarlo, una sola vez:

1. Genera un PAT en https://github.com/settings/tokens/new?scopes=public_repo&description=mcp-aemps-registry-sync
   (scope **`public_repo`** es suficiente, NO uses `repo` que da más permisos).
2. Copia el token.
3. Ve a `Settings → Secrets and variables → Actions → New repository secret`
   en https://github.com/romanpert/mcp-aemps/settings/secrets/actions
4. Name: `MCP_REGISTRY_PAT`. Value: pega el token. Guarda.

A partir del próximo `git push origin vX.Y.Z`, el workflow:
- Sincroniza tu fork `romanpert/mcp-registry` con upstream `main`
- Crea rama `bump-mcp-aemps-X.Y.Z` con `server.yaml` actualizado
  (commit SHA inyectado del release)
- Empuja la rama a tu fork
- Abre/actualiza PR contra `docker/mcp-registry` con título "Bump mcp-aemps to X.Y.Z"

El primer PR (initial submission) se hace manualmente con los pasos arriba.
Los siguientes son completamente automáticos.
