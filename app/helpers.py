# app/helpers

from typing import Any, Dict, Optional, Literal, Tuple
from datetime import datetime, timezone
from fastapi import HTTPException
import asyncio
import json
import logging
import re
import unicodedata

import httpx
import pandas as pd

from app.config import settings

API_CIMA_AEMPS_VERSION = "1.23"
# VERSION API CIMA
API_PSUM_VERSION = "2.0"

MAX_LOG_BODY = 2_000
SENSITIVE_KEYS = {"token", "authorization", "auth", "api_key", "apikey", "key", "password", "pwd", "secret"}

CN_MIN = 600000
CN_MAX = 999999
CN_RE  = re.compile(r"^\d{6}$")

HTML_BASE_URL = "https://cima.aemps.es/cima"

# Mapa tipo_doc → (slug_path, prefijo_fichero)
_DOC_HTML_INFO: dict[int, tuple[str, str]] = {
    1: ("ft",  "FT"),
    2: ("p",   "P"),
    3: ("ipe", "IPE"),
    4: ("ipt", "IPT"),
}

logger = logging.getLogger(__name__)
if logger.isEnabledFor(logging.DEBUG):
    logger.debug("Config (safe): %s", settings.safe_dump())


def build_dochtml_url(
    tipo_doc: int,
    nregistro: str,
    seccion: str | None = None,
    ext: str = "html",
) -> str:
    """
    Construye un enlace estable a la ficha/prospecto HTML de CIMA:

      https://cima.aemps.es/cima/dochtml/{slug}/{nregistro}/{PREFIJO}_{nregistro}.{ext}#{seccion?}

    Ejemplo:
      tipo_doc=1, nregistro='25670', seccion='4.5'
      → https://cima.aemps.es/cima/dochtml/ft/25670/FT_25670.html#4.5
    """
    slug, prefix = _DOC_HTML_INFO.get(tipo_doc, (str(tipo_doc), str(tipo_doc).upper()))

    base = f"{HTML_BASE_URL}/dochtml/{slug}/{nregistro}/{prefix}_{nregistro}.{ext}"
    if seccion:
        return f"{base}#{seccion}"
    return base


def _redact_query_params(params: Any) -> Any:
    try:
        if hasattr(params, "items"):
            out = {}
            for k, v in params.items():
                if str(k).lower() in SENSITIVE_KEYS:
                    out[k] = "***REDACTED***"
                else:
                    out[k] = v
            return out
    except Exception:
        pass
    return params


def _redact_url(url: Any) -> str:
    # Ofusca credenciales en scheme://user:pass@host...
    try:
        s = str(url)
        return re.sub(r"(://)([^:@/\s]+):([^@/\s]+)@", r"\1\2:***REDACTED***@", s)
    except Exception:
        return str(url)


def _truncate(s: Optional[str], limit: int = MAX_LOG_BODY) -> str:
    if not s:
        return ""
    return s if len(s) <= limit else s[:limit] + "…[truncated]"


def format_response(resultado: Any, metadatos: Dict[str, Any], fanout: bool = False) -> Any:
    if resultado is None:
        return {"data": None, **metadatos}

    if isinstance(resultado, list):
        if not fanout:
            return {"data": resultado, **metadatos}
        # fanout=True conserva el comportamiento de inyectar metadatos por item
        lista = []
        for item in resultado:
            if isinstance(item, dict):
                lista.append({**item, **metadatos})
            else:
                lista.append({"data": item, **metadatos})
        return lista

    if isinstance(resultado, dict):
        return {**resultado, **metadatos}

    return {"data": resultado, **metadatos}


def _build_metadata(
    parametros_busqueda: Dict[str, Any],
    version_api: str = API_CIMA_AEMPS_VERSION,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Construye la estructura de metadatos común para las respuestas.
    Puede recibir `extra` para añadir campos adicionales, por ejemplo enlaces.
    """
    fecha_hoy = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    metadata: Dict[str, Any] = {
        "fuente": "CIMA (AEMPS)",
        "fecha_consulta": fecha_hoy,
        "parametros_busqueda": parametros_busqueda,
        "version_api": version_api,
        "descargo_responsabilidad": {
            "texto": "Esta información no constituye consejo médico; se proporciona solo a efectos informativos.",
            "uso_responsable": "Consulte siempre con un profesional sanitario antes de tomar decisiones médicas.",
        },
    }

    if extra:
        # Añadimos las claves extra directamente en metadata
        # (por ejemplo: {"enlaces": {...}})
        metadata.update(extra)

    return {"metadata": metadata}

def parse_cima_fechas(item: Dict[str, Any]) -> None:
    """Parse CIMA timestamp fields in-place for a single result dict.

    Handles: estado.*, docs[*].fecha, fotos[*].fecha,
    presentaciones[*].estado.*, detalleProblemaSuministro.ini/fini.
    """
    import app.cima_client as cima

    if not isinstance(item, dict):
        return

    estado = item.get("estado")
    if isinstance(estado, dict):
        for key in list(estado):
            estado[key] = cima._parse_fecha(estado[key])

    for doc in item.get("docs", []):
        if "fecha" in doc:
            doc["fecha"] = cima._parse_fecha(doc["fecha"])

    for foto in item.get("fotos", []):
        if "fecha" in foto:
            foto["fecha"] = cima._parse_fecha(foto["fecha"])

    for pres in item.get("presentaciones", []):
        pres_estado = pres.get("estado")
        if isinstance(pres_estado, dict):
            for key in list(pres_estado):
                pres_estado[key] = cima._parse_fecha(pres_estado[key])

    dps = item.get("detalleProblemaSuministro")
    if isinstance(dps, dict):
        for key in ("ini", "fini"):
            if key in dps:
                dps[key] = cima._parse_fecha(dps[key])


def parse_cima_fechas_list(items: list) -> None:
    """Parse CIMA timestamp fields in-place for a list of result dicts."""
    for item in items:
        parse_cima_fechas(item)


def _filter_exact(df: pd.DataFrame, column: str, value: str) -> pd.DataFrame:
    return df[df[column].astype(str) == value]


def _filter_contains(df: pd.DataFrame, column: str, value: str) -> pd.DataFrame:
    # evita petar con columnas no-string
    return df[df[column].astype(str).str.contains(str(value), case=False, na=False)]


def _filter_bool(df: pd.DataFrame, column: str, flag: bool) -> pd.DataFrame:
    val = "SI" if flag else "NO"
    return df[df[column] == val]


def _filter_numeric(
    df: pd.DataFrame, column: str, min_val: Optional[float], max_val: Optional[float]
) -> pd.DataFrame:
    series = pd.to_numeric(df[column], errors="coerce")
    if min_val is not None:
        df = df[series >= float(min_val)]
    if max_val is not None:
        df = df[series <= float(max_val)]
    return df


def _paginate(df: pd.DataFrame, page: int, page_size: int) -> pd.DataFrame:
    page = max(1, int(page))
    page_size = max(1, int(page_size))
    start = (page - 1) * page_size
    return df.iloc[start : start + page_size]


def _filter_date(df: pd.DataFrame, column: str, date_str: str, op: Literal["ge", "le"]) -> pd.DataFrame:
    d = datetime.strptime(date_str, "%d/%m/%Y")
    series = pd.to_datetime(df[column], dayfirst=True, errors="coerce")
    if op == "ge":
        return df[series >= d]
    return df[series <= d]


# AUX FUNCTION
def _normalize(s: Optional[str]) -> str:
    if s is None:
        return ""
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


# Helper para llamadas seguras a cima.*
async def safe_cima_call(func, *args, **kwargs) -> Any:
    """
    Wrapper seguro para llamadas a CIMA con manejo robusto de errores.
    No expone respuestas de terceros al cliente y redacta datos sensibles en logs.
    """
    try:
        result = await func(*args, **kwargs)
        return result

    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        try:
            body = _truncate(json.dumps(exc.response.json(), ensure_ascii=False))
        except Exception:
            body = _truncate(exc.response.text)
        url = _redact_url(getattr(exc.request, "url", "N/A"))
        params = _redact_query_params(getattr(exc.request, "params", {}))

        logger.error(
            "HTTPStatusError en API externa",
            extra={"status": status, "url": str(url), "params": params, "body": body},
        )

        if status == 404:
            logger.info("Recurso no encontrado en API externa", extra={"url": str(url)})
            raise HTTPException(
                status_code=404,
                detail="Recurso no encontrado en API externa"
            )

        if status == 400:
            # No exponer texto de terceros
            raise HTTPException(status_code=400, detail="Parámetros inválidos para API externa (400)")

        # Resto de códigos
        raise HTTPException(status_code=502, detail=f"Error en API externa ({status})")

    except (httpx.RequestError, asyncio.TimeoutError) as exc:
        # No exponer detalle exacto
        logger.error(f"Error de red/timeout con API externa: {exc.__class__.__name__}: {exc}")
        raise HTTPException(
            status_code=503,
            detail="Servicio no disponible: No se pudo conectar con la API externa",
        )

    except ValueError as exc:
        logger.error(f"Error de validación en parámetros: {exc}")
        raise HTTPException(status_code=400, detail="Error en parámetros")

    except Exception:
        logger.exception("Error inesperado en safe_cima_call")
        raise HTTPException(status_code=500, detail="Error interno inesperado procesando solicitud")

def _looks_like_cn(code: str) -> bool:
    """
    Devuelve True si `code` parece un Código Nacional:
    - exactamente 6 dígitos
    - entre 600000 y 999999
    """
    if not code or not CN_RE.fullmatch(code):
        return False
    value = int(code)
    return CN_MIN <= value <= CN_MAX


def _resolve_nregistro_from_cn_df(
    df_presentaciones: pd.DataFrame,
    cn: str,
) -> Optional[str]:
    """
    Resuelve un CN a 'Nº Registro' directamente contra df_presentaciones.
    No conoce nada de FastAPI ni de app.state; solo usa el DataFrame pasado.
    """
    try:
        filt = _filter_exact(df_presentaciones, "Cod. Nacional", str(cn))
    except Exception as e:
        logger.warning(
            "Error usando _filter_exact con CN=%s (%s). Probando filtro manual.",
            cn,
            type(e).__name__,
        )
        filt = df_presentaciones[
            df_presentaciones["Cod. Nacional"].astype(str).str.strip() == str(cn).strip()
        ]

    if filt.empty:
        logger.warning(
            "No se encontró ninguna fila en df_presentaciones para CN=%s", cn
        )
        return None

    row = filt.iloc[0]
    real_nr = str(row.get("Nº Registro") or "").strip()

    if not real_nr:
        logger.warning(
            "Fila encontrada para CN=%s pero sin 'Nº Registro' válido en df_presentaciones",
            cn,
        )
        return None

    return real_nr


def normalize_nregistro_and_cn(
    *,
    nregistro: Optional[str],
    cn: Optional[str],
    df_presentaciones: Optional[pd.DataFrame],
) -> Tuple[Optional[str], Optional[str]]:
    """
    Normaliza identificadores para llamadas a CIMA (docSegmentado/*).

    Reglas:
    - CIMA SOLO acepta 'nregistro' en docSegmentado/secciones y contenido.
    - Si viene un CN:
      - en `cn`, o
      - en `nregistro` con pinta de CN (6 dígitos 600000–999999),
      intentamos resolverlo a 'Nº Registro' mirando df_presentaciones.

    Devuelve:
      (nregistro_normalizado, cn_normalizado)

    Donde:
      - nregistro_normalizado es válido para CIMA o None si no se pudo resolver.
      - cn_normalizado es el CN “canónico” si se detectó alguno (aunque no se pudiera resolver).
    """

    original_nregistro = nregistro
    original_cn = cn

    # 1) Elegimos candidato de CN
    candidate_cn: Optional[str] = None

    # Prioridad: cn explícito
    if cn:
        candidate_cn = cn
    # Si no hay cn explícito, miramos si nregistro parece CN
    elif nregistro and _looks_like_cn(nregistro):
        candidate_cn = nregistro

    # 2) Casos donde YA tenemos un nregistro que claramente NO es CN
    #    (ej: nregistro="70039", cn="661426")
    if nregistro and not _looks_like_cn(nregistro):
        # Este nº de registro ya es utilizable para CIMA; solo normalizamos cn
        return nregistro, original_cn or candidate_cn

    # 3) Si no hay ningún CN candidato, no tocamos nada
    if candidate_cn is None:
        return nregistro, cn

    # 4) A partir de aquí, queremos mapear CN → nregistro usando el DF
    if df_presentaciones is None:
        logger.warning(
            "normalize_nregistro_and_cn: df_presentaciones=None; "
            "no se puede resolver CN=%s",
            candidate_cn,
        )
        # No devolvemos nregistro “falso”; marcamos solo el CN
        return None, candidate_cn

    real_nr = _resolve_nregistro_from_cn_df(df_presentaciones, candidate_cn)

    if not real_nr:
        logger.warning(
            "No se pudo resolver CN=%s a 'Nº Registro' en df_presentaciones",
            candidate_cn,
        )
        # No devolvemos nregistro inventado; solo el CN detectado
        return None, candidate_cn

    logger.info(
        "Resuelto CN=%s → nregistro=%s vía df_presentaciones",
        candidate_cn,
        real_nr,
    )

    return real_nr, candidate_cn

