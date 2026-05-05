# app/config.py
"""Pydantic settings loaded from environment / .env.

The server runs with zero required env vars. Redis (or any Redis-compatible
store like Valkey) is optional — if ``REDIS_URL`` (or
``redis_password+redis_host``) is unset, the server uses in-memory cache
and rate limiting and continues to work normally.
"""

from __future__ import annotations

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

    uvicorn_host: str = Field("0.0.0.0", description="Uvicorn bind host")
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
    log_dir: str = Field("./logs", description="Log directory")
    log_stacktraces: bool = Field(False, description="Print tracebacks in logs")

    allowed_origins: Annotated[List[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"],
        description="CORS allowed origins",
    )

    max_results: int = Field(30, description="Maximum results per page")

    metrics_key: Optional[SecretStr] = Field(
        None,
        description="If set, /internal/metrics requires a matching X-Metrics-Key header.",
    )

    @field_validator("allowed_origins", mode="before")
    def split_allowed_origins(cls, v):
        if isinstance(v, str):
            return [u.strip() for u in v.split(",") if u.strip()]
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
        try:
            return _mkdir_private(v)
        except Exception as e:
            raise ValueError(f"Could not prepare log dir '{v}': {e}")

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
