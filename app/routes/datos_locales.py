# mcp_aemps/app/routes/datos_locales.py
# System-level endpoints (no external CIMA calls)
from __future__ import annotations

from fastapi import APIRouter
import app.mcp_constants as constant
from app.rate_limits import limit_local

router = APIRouter()


@router.get(
    "/system-info-prompt",
    tags=["Prompts"],
    operation_id="get_system_info_prompt",
    summary="Obtener el Prompt del sistema para el agente MCP",
    dependencies=[limit_local],
)
async def get_system_prompt() -> str:
    return constant.MCP_AEMPS_SYSTEM_PROMPT
