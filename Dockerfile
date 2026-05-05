FROM python:3.13-slim

# Evitar warnings y salida con buffer
ENV PIP_ROOT_USER_ACTION=ignore \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Dependencias de sistema
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libmagic1 jq curl ca-certificates wget \
 && rm -rf /var/lib/apt/lists/*

# ----- Crear usuario no-root y preparar directorios -----
ARG APP_USER=appuser
ARG APP_UID=10001
RUN useradd -u ${APP_UID} -m -s /usr/sbin/nologin ${APP_USER} \
 && mkdir -p /app /data /app/logs \
 && chown -R ${APP_USER}:${APP_USER} /app /data \
 && chmod 700 /data /app/logs

WORKDIR /app

# ----- Copiar dependencias -----
COPY requirements.txt pyproject.toml ./

# ----- Instalar dependencias -----
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# ----- Copiar código -----
COPY app/ ./app/

# ----- Instalar en modo editable -----
RUN pip install --no-cache-dir -e .

# ----- Exponer puerto -----
EXPOSE 8000

# ----- Cambiar a usuario no-root -----
USER ${APP_USER}

# ----- Healthcheck de la app -----
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=5 \
  CMD wget -qO- http://127.0.0.1:8000/health || exit 1


# 3A) Arranque de Uvicorn
#    --app-dir /app indica a Uvicorn dónde buscar el módulo Python
# CMD ["uvicorn", "app/mcp_aemps_server:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "/app"]

# 3B) Arranque con CLI
# Arranque con CLI leyendo UVICORN_HOST y PORT del entorno
CMD ["sh", "-c", "\
  echo \"Arrancando en ${UVICORN_HOST}:${PORT}…\" && \
    mcp_aemps up \
      --uvicorn-host \"${UVICORN_HOST}\" \
      --port         \"${PORT}\" \
      --access-host  \"${ACCESS_HOST:-localhost}\" \
"]