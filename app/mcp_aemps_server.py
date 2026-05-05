# app/mcp_aemps_server.py
"""ASGI entry point used by uvicorn (`app.mcp_aemps_server:app`).

The actual app is built by `app.factory.create_app()`. Enterprise editions
should NOT import this module — they import `create_app` directly and pass
their own extension routers/middleware/hooks.
"""

from __future__ import annotations

from app.factory import create_app

app = create_app()
