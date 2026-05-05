"""End-to-end smoke tests — app boots, /health works, OpenAPI exposes endpoints."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.factory import create_app


def test_health_endpoint_returns_ok() -> None:
    app = create_app(mount_mcp=False)
    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "version" in body
        assert body["cache"] in ("in-memory", "redis")


def test_openapi_exposes_official_cima_endpoints() -> None:
    app = create_app(mount_mcp=False)
    with TestClient(app) as client:
        spec = client.get("/openapi.json").json()
        paths = spec.get("paths", {})

        required = {
            "/medicamento",
            "/medicamentos",
            "/presentaciones",
            "/maestras",
            "/vmpp",
            "/registro-cambios",
            "/problemas-suministro",
            "/problemas-suministro/dcp/{cod_dcp}",
            "/problemas-suministro/dcpf/{cod_dcpf}",
            "/notas",
            "/materiales",
            "/doc-secciones/{tipo_doc}",
            "/doc-contenido/{tipo_doc}",
        }
        missing = required - set(paths)
        assert not missing, f"Missing official CIMA endpoints in OpenAPI: {missing}"


def test_create_app_accepts_extra_routers() -> None:
    """Factory must allow Enterprise edition to inject extra routers."""
    from fastapi import APIRouter

    extra = APIRouter()

    @extra.get("/_premium/audit")
    async def audit():
        return {"ok": True}

    app = create_app(extra_routers=[extra], mount_mcp=False)
    with TestClient(app) as client:
        assert client.get("/_premium/audit").status_code == 200
        # Core still works
        assert client.get("/health").status_code == 200


def test_lifespan_hooks_run() -> None:
    """Startup and shutdown hooks must be invoked in order."""
    from fastapi import FastAPI

    calls: list[str] = []

    async def startup_hook(app: FastAPI) -> None:
        calls.append("startup")

    async def shutdown_hook(app: FastAPI) -> None:
        calls.append("shutdown")

    app = create_app(
        startup_hooks=[startup_hook],
        shutdown_hooks=[shutdown_hook],
        mount_mcp=False,
    )
    with TestClient(app):
        pass

    assert calls == ["startup", "shutdown"]
