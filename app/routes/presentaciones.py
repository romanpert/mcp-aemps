# mcp_aemps/app/routes/presentaciones.py
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import pandas as pd

router = APIRouter(prefix="/internal/aemps", tags=["internal-aemps"])

# Modelo de salida con nombres "limpios"
class Presentacion(BaseModel):
    num_registro: str
    cod_nacional: str
    presentacion: str
    laboratorio: Optional[str] = None
    estado: Optional[str] = None
    cod_atc: Optional[str] = None
    principios_activos: Optional[str] = None

# Mapeo columnas Excel -> nombres internos
COLUMNS_MAP = {
    "Nº Registro": "num_registro",
    "Cod. Nacional": "cod_nacional",
    "Presentación": "presentacion",
    "Laboratorio": "laboratorio",
    "Estado": "estado",
    "Cód. ATC": "cod_atc",
    "Principios Activos": "principios_activos",
}


@router.get(
    "/presentaciones",
    response_model=List[Presentacion],
    summary="Datos de Presentaciones filtrados para uso interno",
)
async def get_presentaciones(request: Request):
    df: pd.DataFrame = getattr(request.app.state, "df_presentaciones", None)

    if df is None or df.empty:
        raise HTTPException(status_code=503, detail="Datos de Presentaciones no disponibles")

    missing = [c for c in COLUMNS_MAP.keys() if c not in df.columns]
    if missing:
        raise HTTPException(
            status_code=500,
            detail=f"Estructura de Presentaciones.xls inesperada. Faltan columnas: {', '.join(missing)}",
        )

    # Sub-dataframe con solo las columnas permitidas
    sub = df[list(COLUMNS_MAP.keys())].rename(columns=COLUMNS_MAP).copy()

    # Tipos seguros (normalmente interesa conservarlo todo como string)
    for col in sub.columns:
        sub[col] = sub[col].astype(str)

    records = sub.to_dict(orient="records")
    return [Presentacion(**r) for r in records]
