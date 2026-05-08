# app/config.py
"""Pydantic settings loaded from environment / .env.

The server runs with zero required env vars. Redis (or any Redis-compatible
store like Valkey) is optional — if ``REDIS_URL`` (or
``redis_password+redis_host``) is unset, the server uses in-memory cache
and rate limiting and continues to work normally.
"""

from __future__ import annotations

import os
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path
from typing import Annotated, List, Optional
from urllib.parse import quote, urlparse

from pydantic import AnyUrl, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

ROOT_DIR = Path(__file__).parent.parent


def _resolve_version() -> str:
    """Read installed package version; fall back gracefully when running from source."""
    try:
        return _pkg_version("mcp-aemps")
    except PackageNotFoundError:
        return "0.0.0+source"


def _detect_default_locale() -> str:
    """Sniff OS locale env vars and return ``"en"`` for English systems,
    ``"es"`` for everything else. Falls back to ``"es"`` because CIMA's
    native data language is Spanish — keeping the default localised to
    the source-of-truth language is the right behaviour when no signal
    is available.

    This is only consulted when ``MCP_AEMPS_LOCALE`` is **not** set
    explicitly — pydantic-settings' env var precedence means an explicit
    value always wins over this default factory.
    """
    for var in ("LC_ALL", "LANG", "LANGUAGE"):
        raw = os.environ.get(var, "")
        if not raw:
            continue
        # Strip codeset (.UTF-8) and modifier (@euro), take the language tag.
        primary = raw.split(".")[0].split("@")[0].split(":")[0]
        lang = primary.split("_")[0].lower()
        if lang.startswith("en"):
            return "en"
        if lang.startswith("es"):
            return "es"
    return "es"


def _default_log_dir() -> str:
    """Per-user, writable-by-default log directory.

    Uses ``app.runtime_state.state_dir()`` so the path matches the rest
    of the per-user runtime artefacts (PID file, runtime.json) — one
    directory per user, OS-canonical:

    - Linux:   ``$XDG_STATE_HOME/mcp-aemps/logs`` (or ``~/.local/state/...``)
    - macOS:   ``~/Library/Application Support/mcp-aemps/logs``
    - Windows: ``%LOCALAPPDATA%\\mcp-aemps\\logs``

    Critical for the Claude Desktop / uvx launch path: the host process
    spawns ``uvx mcp-aemps stdio`` with CWD wherever Claude Desktop
    happens to be (often a system path with no write access). The old
    default ``./logs`` mkdir'ed there and crashed Settings construction
    with ``WinError 5: Access denied``, taking the whole server down.
    """
    # Imported here (and not at module top) to avoid a circular: settings
    # is imported by some modules at import time. ``runtime_state`` is
    # standalone with no project deps so it's safe at call time.
    from app.runtime_state import state_dir

    return str(state_dir() / "logs")


def _mkdir_private(path_str: str) -> str:
    p = Path(path_str)
    p.mkdir(parents=True, exist_ok=True)
    try:
        p.chmod(0o700)
    except Exception:
        pass
    return str(p.resolve())


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    mcp_aemps_version: str = Field(default_factory=_resolve_version, description="Server version")

    # Locale for LLM-facing tool descriptions, system prompt, prompt
    # descriptions / bodies and resource descriptions. CIMA's native
    # language is Spanish; the default is therefore "es" unless the OS
    # signals an English environment via $LC_ALL / $LANG / $LANGUAGE.
    # An explicit MCP_AEMPS_LOCALE env var always wins over the sniff.
    mcp_aemps_locale: str = Field(
        default_factory=_detect_default_locale,
        description='LLM-facing language: "es" or "en". Auto-sniffed from $LANG/$LC_ALL when unset.',
    )

    # Optional OAuth 2.1 Resource-Server mode. When OFF (default), every
    # request is unauthenticated — fine for self-hosted public deployments
    # since CIMA itself is public. When ON, every MCP tool call (HTTP at
    # /mcp; stdio is unaffected — stdio is process-local) requires a valid
    # Bearer token issued by the configured Authorization Server, plus the
    # required scopes. The Protected Resource Metadata document is exposed
    # at /.well-known/oauth-protected-resource (RFC 9728) so any
    # spec-compliant MCP client can discover the AS via DCR (RFC 7591).
    oauth_enabled: bool = Field(False, description="Enable OAuth 2.1 RS mode")
    oauth_issuer: Optional[str] = Field(
        None, description="OAuth Authorization Server issuer URL (e.g. https://auth.example.com)"
    )
    oauth_jwks_url: Optional[str] = Field(None, description="JWKS endpoint of the Authorization Server")
    oauth_audience: Optional[str] = Field(
        None,
        description="Expected `aud` claim of issued tokens (this server's resource indicator)",
    )
    oauth_required_scopes: Annotated[List[str], NoDecode] = Field(
        default_factory=lambda: ["mcp:read"],
        description="Required scopes (comma-separated env var)",
    )

    # Secure-by-default since v0.4.16: bind to loopback only. The previous
    # default ``0.0.0.0`` was a footgun on multi-tenant networks (any
    # neighbour on the LAN could reach the listener; CIMA data is public
    # but the principle is fail-closed). Docker / reverse-proxy deployments
    # opt back into LAN exposure with ``mcp_aemps up --bind-all`` (CLI) or
    # ``UVICORN_HOST=0.0.0.0`` (env).
    uvicorn_host: str = Field("127.0.0.1", description="Uvicorn bind host")
    access_host: str = Field("localhost", description="Public host clients use")
    port: int = Field(8000, description="TCP port")

    # Redis (or Valkey) is OPTIONAL. Default in-memory; production deployments
    # typically set REDIS_URL for distributed cache + rate limiting.
    redis_host: Optional[str] = Field(None, description="Redis host (optional)")
    redis_port: int = Field(6379, description="Redis port")
    redis_user: str = Field("default", description="Redis user")
    redis_password: Optional[SecretStr] = Field(None, description="Redis password (optional)")
    redis_url: Optional[AnyUrl] = Field(
        None, description="Full Redis connection string (auto-built if not provided)"
    )

    log_level: str = Field("INFO", description="Logging level")
    log_retention_days: int = Field(90, description="Log retention in days")
    log_dir: str = Field(
        default_factory=_default_log_dir,
        description=(
            "Log directory. Defaults to a per-user writable path "
            "matching app.runtime_state.state_dir(); falls back to "
            "the system temp dir if that path is not writable, and "
            "finally degrades to console-only logging. Set explicitly "
            "to override (e.g. ``LOG_DIR=/var/log/mcp-aemps``)."
        ),
    )
    log_stacktraces: bool = Field(False, description="Print tracebacks in logs")

    allowed_origins: Annotated[List[str], NoDecode] = Field(
        default_factory=list,
        description=(
            "CORS allowed origins. Empty by default — the server is not "
            "intended to be reached from a browser; MCP clients call it "
            "from server-side code or local IPC. Set explicitly (CSV "
            "or JSON list) if you front-end mcp-aemps from a webapp."
        ),
    )

    # MCP transport security (DNS rebinding protection on the
    # Streamable-HTTP /mcp endpoint). FastMCP ≥ 1.27 auto-enables this
    # when host is localhost-y, with a default allowed_hosts list that
    # rejects everything else (including FastAPI's TestClient
    # ``testserver`` synthetic host). We expose a kill-switch + override
    # so deployers can either disable it (CIMA data is public, the
    # attack vector is low-impact) or extend the host list to cover
    # their reverse-proxy hostname.
    # Secure-by-default since v0.4.16: protection ON. The default
    # ``allowed_hosts`` list (see ``app/stdio_server.py``) covers
    # ``localhost``, ``127.0.0.1``, ``[::1]`` and FastAPI TestClient's
    # synthetic ``testserver`` host, so dev / test workflows don't break.
    # Reverse-proxy deployments must extend the host list via
    # ``MCP_AEMPS_ALLOWED_HOSTS`` regardless — the flag flip just forces
    # them to think about it instead of silently accepting any Host header.
    mcp_aemps_dns_rebinding_protection: bool = Field(
        True,
        description=(
            "Enable MCP transport DNS rebinding protection (Host/Origin "
            "header validation on /mcp). Default on — reverse-proxy "
            "deployments must extend MCP_AEMPS_ALLOWED_HOSTS / "
            "MCP_AEMPS_ALLOWED_ORIGINS to whitelist their public hostname. "
            "Set to false to disable (CIMA data is public so the residual "
            "risk is low, but secure-by-default is the right posture)."
        ),
    )
    mcp_aemps_allowed_hosts: Annotated[List[str], NoDecode] = Field(
        default_factory=list,
        description=(
            "Comma-separated Host header values allowed on /mcp when DNS "
            "rebinding protection is on. Wildcard ports supported "
            "(``localhost:*``)."
        ),
    )
    mcp_aemps_allowed_origins: Annotated[List[str], NoDecode] = Field(
        default_factory=list,
        description=(
            "Comma-separated Origin header values allowed on /mcp when DNS rebinding protection is on."
        ),
    )

    max_results: int = Field(30, description="Maximum results per page")

    metrics_key: Optional[SecretStr] = Field(
        None,
        description=(
            "Required to enable /internal/metrics. When unset (default), "
            "the endpoint returns 503 (fail-closed since v0.4.16). When "
            "set, requests must carry a matching X-Metrics-Key header."
        ),
    )

    @field_validator(
        "allowed_origins",
        "mcp_aemps_allowed_hosts",
        "mcp_aemps_allowed_origins",
        mode="before",
    )
    def split_csv_lists(cls, v):
        if isinstance(v, str):
            return [u.strip() for u in v.split(",") if u.strip()]
        return v

    @field_validator("oauth_required_scopes", mode="before")
    def split_oauth_scopes(cls, v):
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    @field_validator("mcp_aemps_locale", mode="after")
    def normalise_locale(cls, v):
        v = (v or "es").strip().lower()
        if v not in {"es", "en"}:
            raise ValueError(f"MCP_AEMPS_LOCALE must be 'es' or 'en', got {v!r}")
        return v

    @field_validator("allowed_origins", mode="after")
    def validate_origins(cls, v):
        if v == ["*"] or (len(v) == 1 and v[0] == "*"):
            return ["*"]
        if "*" in v:
            raise ValueError("Do not mix '*' with explicit origins in ALLOWED_ORIGINS")
        for u in v:
            pr = urlparse(u)
            if pr.scheme not in {"http", "https"} or not pr.netloc:
                raise ValueError(f"Invalid CORS origin: {u}")
        return v

    @field_validator("redis_url", mode="before")
    def assemble_redis_url(cls, v, info):
        if v is not None:
            return v
        data = info.data
        password = data.get("redis_password")
        host = data.get("redis_host")
        if not password or not host:
            return None
        user = data.get("redis_user") or "default"
        pwd = password.get_secret_value() if isinstance(password, SecretStr) else str(password)
        port = data.get("redis_port")
        return f"redis://{quote(user)}:{quote(pwd)}@{host}:{port}/0"

    @field_validator("port")
    def port_must_be_valid(cls, v):
        if not (1 <= v <= 65535):
            raise ValueError("Port must be between 1 and 65535")
        return v

    @field_validator("log_dir")
    def ensure_log_dir_exists(cls, v):
        """Best-effort log dir resolution. NEVER raises — settings
        construction must always succeed so the server can boot under
        adverse environments (Claude Desktop launching uvx with a
        read-only CWD, Docker without a volume mount, sandboxed
        contexts).

        Order:
          1. The configured/default path.
          2. ``tempfile.gettempdir()`` / ``mcp-aemps-logs``.
          3. Empty string — ``logging_setup`` then skips the file
             handler entirely (console-only logging)."""
        import tempfile

        for candidate in (v, str(Path(tempfile.gettempdir()) / "mcp-aemps-logs")):
            if not candidate:
                continue
            try:
                return _mkdir_private(candidate)
            except Exception:
                continue
        # Last resort: console-only. logging_setup handles "" by
        # skipping the rotating file handler.
        return ""

    @field_validator("log_level")
    def validate_log_level(cls, v):
        allowed = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
        vv = v.upper()
        if vv not in allowed:
            raise ValueError(f"log_level must be one of {sorted(allowed)}")
        return vv

    @field_validator("max_results")
    def max_results_reasonable(cls, v):
        if not isinstance(v, int) or v <= 0:
            raise ValueError("max_results must be a positive integer")
        if v > 1000:
            raise ValueError("max_results must not exceed 1000")
        return v

    @field_validator("log_retention_days")
    def validate_retention(cls, v):
        if not isinstance(v, int) or v < 1:
            raise ValueError("log_retention_days must be >= 1")
        if v > 3650:
            raise ValueError("log_retention_days must not exceed 3650")
        return v

    def safe_dump(self) -> dict:
        return self.model_dump(
            exclude={"redis_password", "redis_url", "metrics_key"},
            exclude_none=True,
        )


settings = Settings()
