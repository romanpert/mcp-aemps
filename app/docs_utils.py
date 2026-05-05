# app/docs_utils.py
"""
Utilidades asíncronas para obtener y gestionar descargas de la AEMPS.
Endurecido: escrituras atómicas, permisos 0600, filenames seguros y logs discretos.
"""
from __future__ import annotations

import os
import re
import logging
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse, unquote
from pathlib import Path
import asyncio
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


def get_presentaciones_url() -> str:
    """
    URL para descargar Presentaciones de la AEMPS.
    https://cima.aemps.es/cima/publico/nomenclator.html
    """
    return "https://listadomedicamentos.aemps.gob.es/Presentaciones.xls"


def get_nomenclator_url() -> str:
    """
    URL para descargar el CSV de Nomenclátor de la AEMPS.
    """
    base = "https://www.sanidad.gob.es/profesionales/nomenclator.do"
    params = {
        "metodo": "buscarProductos",
        "especialidad": "%%%",      # httpx lo convertirá en %25%25%25
        "d-4015021-e": "1",
        "6578706f7274": "1",
    }
    return str(httpx.URL(base, params=params))


# ---------- helpers de seguridad / IO ----------

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")

def _safe_filename(name: str, default: str = "download.bin") -> str:
    """
    Sanitiza el nombre de fichero: evita paths, quita caracteres raros y recorta longitud.
    """
    name = os.path.basename(name or "").strip()
    if not name:
        return default
    name = _SAFE_NAME_RE.sub("_", name)
    # Evitar nombres tipo "." o ".."
    if name in {".", ".."}:
        return default
    # Longitud razonable
    return name[:200]


def _atomic_replace(src: Path, dst: Path) -> None:
    """
    Reemplazo atómico dentro del mismo filesystem.
    """
    src.replace(dst)
    try:
        os.chmod(dst, 0o600)
    except Exception:
        pass


async def _stream_to_atomic_file(resp: httpx.Response, dest_path: Path, chunk: int = 32_768) -> Path:
    tmp = dest_path.with_suffix(dest_path.suffix + ".part")
    try:
        with open(tmp, "wb") as fd:
            async for data in resp.aiter_bytes(chunk_size=chunk):
                fd.write(data)
        _atomic_replace(tmp, dest_path)
        return dest_path
    except Exception:
        # best-effort cleanup
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        raise


def _log_download_done(file_path: Path) -> None:
    """
    Log discreto: nombre y tamaño; ruta completa solo en DEBUG.
    """
    try:
        size = file_path.stat().st_size
    except Exception:
        size = -1
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("Descarga completada: %s (%s bytes)", str(file_path), size)
    else:
        logger.info("Descarga completada: %s (%s bytes)", file_path.name, size)


def _validate_https_url(url: str) -> None:
    pr = urlparse(url)
    if pr.scheme.lower() != "https" or not pr.netloc:
        raise ValueError("URL inválida o no segura (se requiere https)")


# ---------- descargas ----------
async def download_presentaciones(dest_path: Path, timeout: int = 60, max_retries: int = 3) -> Path:
    url = get_presentaciones_url()
    _validate_https_url(url)

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    timeout_cfg = httpx.Timeout(connect=10.0, read=float(timeout), write=60.0, pool=None)

    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout_cfg, follow_redirects=True, trust_env=True) as client:
                async with client.stream("GET", url) as resp:
                    resp.raise_for_status()
                    await _stream_to_atomic_file(resp, dest_path)
            _log_download_done(dest_path)
            return dest_path
        except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.ConnectError) as e:
            last_err = e
            logger.warning("Intento %s/%s fallido descargando Presentaciones.xls: %s", attempt, max_retries, e)
            if attempt < max_retries:
                await asyncio.sleep(2 ** (attempt - 1))
        except httpx.HTTPError as e:
            logger.error("Error HTTP descargando Presentaciones.xls: %s", e)
            raise
    # agotados reintentos
    raise httpx.ConnectError(str(last_err))  # se gestionará en startup con caché local

async def download_nomenclator_csv(
    dest_dir: Path,
    url: Optional[str] = None,
    timeout: int = 60,
    max_retries: int = 3,
) -> Path:
    """
    Descarga asíncrona del CSV de Nomenclátor, gestiona filenames y caché local:
    - Usa HEAD para extraer Content-Disposition (mejor nombre, fecha).
    - Si existe CSV igual o más reciente, no descarga.
    - Elimina CSVs antiguos si procede.
    - Escritura atómica + permisos 0600.
    - Timeouts y reintentos con backoff exponencial.
    """
    url = (url or get_nomenclator_url()).strip()
    _validate_https_url(url)

    dest_dir.mkdir(parents=True, exist_ok=True)
    timeout_cfg = httpx.Timeout(connect=10.0, read=float(timeout), write=60.0, pool=None)

    for attempt in range(1, max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout_cfg, follow_redirects=True) as client:
                # 1) HEAD para Content-Disposition (si falla, continúa)
                head = None
                try:
                    head = await client.head(url)
                    head.raise_for_status()
                except httpx.HTTPError:
                    logger.debug("HEAD falló; se intentará GET directo")

                # 2) Streaming GET
                async with client.stream("GET", url) as resp:
                    resp.raise_for_status()

                    # 3) Determinar filename
                    cd = (head.headers.get("content-disposition", "") if head else resp.headers.get("content-disposition", ""))
                    m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^\";]+)"?', cd)
                    if m:
                        filename_raw = unquote(m.group(1))
                    else:
                        # Fallback: fecha + basename de la URL
                        last_mod = (head or resp).headers.get("last-modified", "")
                        try:
                            dt = parsedate_to_datetime(last_mod) if last_mod else datetime.utcnow()
                        except Exception:
                            dt = datetime.utcnow()
                        date_str = dt.strftime("%Y%m%d")
                        base = os.path.basename(urlparse(url).path) or "nomenclator.csv"
                        filename_raw = f"{date_str}_{base}"

                    filename = _safe_filename(filename_raw, "nomenclator.csv")

                    # 4) Comprobar caché local
                    prefix = re.match(r"(\d{8})", filename)
                    new_date = prefix.group(1) if prefix else None
                    existing = sorted(
                        [f for f in os.listdir(dest_dir) if f.lower().endswith(".csv")],
                        reverse=True
                    )
                    for f in existing:
                        mf = re.match(r"(\d{8})", f)
                        if mf and new_date and mf.group(1) >= new_date:
                            chosen = dest_dir / f
                            if logger.isEnabledFor(logging.DEBUG):
                                logger.debug("Reusando CSV existente: %s", chosen)
                            else:
                                logger.info("CSV existente igual/reciente: %s", Path(f).name)
                            return chosen

                    # 5) Borrar antiguos
                    for f in existing:
                        mf = re.match(r"(\d{8})", f)
                        if not mf or (new_date and mf.group(1) < new_date):
                            try:
                                (dest_dir / f).unlink(missing_ok=True)
                                logger.debug("CSV antiguo borrado: %s", f)
                            except Exception:
                                logger.warning("No se pudo borrar viejo CSV: %s", f)

                    # 6) Escribir nuevo archivo por chunks (atómico)
                    dest_path = dest_dir / filename
                    await _stream_to_atomic_file(resp, dest_path)

                    _log_download_done(dest_path)
                    return dest_path

        except (httpx.ReadTimeout, httpx.ConnectTimeout) as e:
            logger.warning("Timeout en intento %s/%s: %s", attempt, max_retries, e)
            if attempt < max_retries:
                backoff = 2 ** (attempt - 1)
                logger.info("Reintentando en %ss…", backoff)
                await asyncio.sleep(backoff)
            else:
                logger.error("Agotados reintentos por timeout; abortando descarga.")
                raise

        except httpx.HTTPError as e:
            logger.error("Error HTTP en descarga CSV: %s", e)
            raise

    # Nunca debería llegar aquí
    raise RuntimeError("No fue posible descargar el CSV de nomenclátor.")
