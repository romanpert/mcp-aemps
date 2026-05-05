# v2/mcp_aemps/app/config.py
from pathlib import Path
from typing import List, Annotated
import os

from dotenv import load_dotenv
from pydantic import AnyUrl, Field, field_validator, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict, NoDecode
from urllib.parse import quote, urlparse

# 1) Carga el .env en memoria
ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / ".env")

def _mkdir_private(path_str: str) -> str:
    p = Path(path_str)
    p.mkdir(parents=True, exist_ok=True)
    try:
        p.chmod(0o700)  # sólo owner
    except Exception:
        pass
    return str(p.resolve())

class Settings(BaseSettings):
    # Configuración de Pydantic v2
    model_config = SettingsConfigDict(
        case_sensitive=False,
    )

    # Versión de la aplicación
    mcp_aemps_version: str = Field("0.1.0", description="Versión del servidor")

    # Servidor
    uvicorn_host: str = Field("0.0.0.0", description="Host donde bindeará Uvicorn")
    access_host: str = Field("localhost", description="Host público para la API")
    port: int = Field(8000, description="Puerto TCP")

    # Redis (host, puerto, usuario y contraseña);
    # luego montamos redis_url automáticamente
    redis_host: str = Field("redis", description="Host de Redis")
    redis_port: int = Field(6379, description="Puerto de Redis")
    redis_user: str = Field("default", description="Usuario Redis")
    redis_password: SecretStr = Field(..., description="Password Redis")
    redis_url: AnyUrl | None = Field(
        None,
        description="Cadena completa de conexión a Redis (se autogenera si no se provee)"
    )
    cache_prefix: str = Field("fastapi-cache", description="Prefijo de cache")
    log_level: str = Field("INFO", description="Nivel de logging")
    log_retention_days: int = Field(90, description="Días de retención de logs")
    log_dir: str = Field("./logs", description="Directorio de logs")
    log_stacktraces: bool = Field(False, description="Imprimir tracebacks en logs")

    # CORS
    allowed_origins: Annotated[List[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"],
        description="Orígenes permitidos para CORS"
    )

    # Datos
    data_dir: str = Field("/data", description="Ruta montada con los datos")

    # Rate limiting
    rate_limit: int = Field(100, description="Peticiones por periodo")
    rate_period: int = Field(60, description="Periodo en segundos")
    max_results: int = Field(30, description="Máximo número de resultados")

    @field_validator("allowed_origins", mode="before")
    def split_allowed_origins(cls, v):
        if isinstance(v, str):
            items = [u.strip() for u in v.split(",") if u.strip()]
            return items
        return v

    @field_validator("allowed_origins", mode="after")
    def validate_origins(cls, v):
        # Permite el comodín, pero no mezclarlo con otros
        if v == ["*"] or (len(v) == 1 and v[0] == "*"):
            return ["*"]
        if "*" in v:
            raise ValueError("No mezcles '*' con orígenes concretos en ALLOWED_ORIGINS")
        # Validar http/https
        valid = []
        from urllib.parse import urlparse
        for u in v:
            pr = urlparse(u)
            if pr.scheme in {"http", "https"} and pr.netloc:
                valid.append(u)
            else:
                raise ValueError(f"Origen CORS inválido: {u}")
        return valid
    
    @field_validator("redis_url", mode="before")
    def assemble_redis_url(cls, v, info):
        if v is not None:
            return v
        data = info.data
        user = data.get("redis_user") or "default"
        pwd  = (data.get("redis_password") or SecretStr("")).get_secret_value()
        host = data.get("redis_host")
        port = data.get("redis_port")
        # Escapar usuario/contraseña por si contienen '@:/#?&%'
        return f"redis://{quote(user)}:{quote(pwd)}@{host}:{port}/0"

    @field_validator("port")
    def port_must_be_valid(cls, v):
        if not (1 <= v <= 65535):
            raise ValueError("El puerto debe estar entre 1 y 65535")
        return v

    @field_validator("data_dir")
    def ensure_data_dir_exists(cls, v):
        try:
            return _mkdir_private(v)
        except Exception as e:
            raise ValueError(f"No se pudo preparar el directorio de datos '{v}': {e}")

    @field_validator("log_dir")
    def ensure_log_dir_exists(cls, v):
        try:
            return _mkdir_private(v)
        except Exception as e:
            raise ValueError(f"No se pudo preparar el directorio de logs '{v}': {e}")
    
    @field_validator("log_level")
    def validate_log_level(cls, v):
        allowed = {"CRITICAL","ERROR","WARNING","INFO","DEBUG"}
        vv = v.upper()
        if vv not in allowed:
            raise ValueError(f"log_level debe ser uno de {sorted(allowed)}")
        return vv
    
    @field_validator("rate_limit","rate_period","max_results")
    def positive_and_reasonable(cls, v, info):
        if not isinstance(v, int) or v <= 0:
            raise ValueError(f"{info.field_name} debe ser un entero positivo")
        # límites suaves para evitar DoS por config
        caps = {"rate_limit": 10_000, "rate_period": 86_400, "max_results": 1_000}
        cap = caps.get(info.field_name)
        if cap and v > cap:
            raise ValueError(f"{info.field_name} no debe exceder {cap}")
        return v
    
    # log_retention_days ≥ 1 (y límite suave opcional)
    @field_validator("log_retention_days")
    def validate_retention(cls, v):
        if not isinstance(v, int) or v < 1:
            raise ValueError("log_retention_days debe ser un entero ≥ 1")
        if v > 3650:  # opcional: 10 años como tope razonable
            raise ValueError("log_retention_days no debe exceder 3650")
        return v

    # Dump seguro para logging (excluye secretos/URLs sensibles)
    def safe_dump(self) -> dict:
        return self.model_dump(
            exclude={"redis_password", "redis_url"},
            exclude_none=True,
        )

# Instanciamos
settings = Settings()