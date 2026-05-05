# app/mcp_aemps_server.py
"""ASGI entry point used by uvicorn (``app.mcp_aemps_server:app``).

The actual app is built by ``app.factory.create_app()``. Downstream consumers
that need to inject routers/middleware/lifecycle hooks should import
``create_app`` directly and pass their extensions instead of importing this
module.
"""

from __future__ import annotations

from app.factory import create_app

app = create_app()
