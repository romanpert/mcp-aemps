# syntax=docker/dockerfile:1.9
# ============================================================================
# mcp-aemps — multi-stage Docker build
# ============================================================================
# Stage 1 (builder): installs deps + builds wheels into a venv
# Stage 2 (runtime): copies the venv on top of a slim base, runs as non-root
# Result: ~150 MB image (was ~280 MB), no build toolchain in final image
# ============================================================================

ARG PYTHON_VERSION=3.13

# ---------- builder ---------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /build

# System deps for building (curl for healthcheck stays in runtime, build-essential only here)
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

# Use uv for faster, deterministic installs
RUN pip install --upgrade pip uv

# Resolve deps first (cacheable layer) — copy only what's needed for resolution
COPY pyproject.toml README.md LICENSE ./
COPY app/ ./app/

# Build a venv with the package + runtime deps
RUN python -m venv /opt/venv \
 && . /opt/venv/bin/activate \
 && uv pip install --strict .

# ---------- runtime ---------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8765 \
    LOG_LEVEL=INFO

# Tools needed at runtime: curl for healthcheck, ca-certificates for HTTPS to CIMA
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Non-root user
ARG APP_UID=10001
ARG APP_USER=appuser
RUN useradd -u ${APP_UID} -m -s /usr/sbin/nologin ${APP_USER} \
 && mkdir -p /app/logs /app/state \
 && chown -R ${APP_USER}:${APP_USER} /app

# Copy the venv from the builder
COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
USER ${APP_USER}

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=5 \
  CMD curl -sf http://127.0.0.1:${PORT}/health || exit 1

# Default: run server in foreground. Override with `docker run ... mcp-aemps <cmd>`.
# ``--bind-all`` flips the (loopback-only since v0.4.16) bind back to 0.0.0.0
# so the container is reachable from outside the container network namespace.
CMD ["sh", "-c", "mcp-aemps up --bind-all --port ${PORT} --no-auto-port"]

# ============================================================================
# OCI labels (image metadata for ghcr.io / docker hub)
# ============================================================================
LABEL org.opencontainers.image.title="mcp-aemps" \
      org.opencontainers.image.description="MCP server for the Spanish AEMPS CIMA pharmaceutical registry" \
      org.opencontainers.image.url="https://github.com/romanpert/mcp-aemps" \
      org.opencontainers.image.source="https://github.com/romanpert/mcp-aemps" \
      org.opencontainers.image.documentation="https://github.com/romanpert/mcp-aemps#readme" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.authors="Román Pérez Dumpert <roman.p98@gmail.com>" \
      org.opencontainers.image.vendor="romanpert"
