# v2/mcp_aemps/app/cli.py – CLI para el servidor MCP-AEMPS
"""💊 CLI del servidor MCP-AEMPS (Agencia Española de Medicamentos y Productos Sanitarios).

Comandos principales
--------------------
• **up**      → arranca el servidor en *modo producción* (sin autoreload).
• **dev**     → arranca el servidor en *modo desarrollo* (con --reload).
• **down**    → detiene un servidor que esté corriendo en background mediante `up`.
• **status**  → comprueba si el servidor está en marcha.
• **restart** → reinicia el servidor (down && up) con los mismos parámetros.
• **logs**    → monitoriza en tiempo real un archivo de logs.
• **health**  → consulta el endpoint `/health` y muestra el estado.
• **openapi** → descarga la especificación OpenAPI (`/openapi.json`).
• **docs**    → abre la documentación Swagger UI en el navegador.

En `app/mcp_aemps.json` se diferencian:
  - `uvicorn_host`: dirección donde bindea Uvicorn (p.ej. "0.0.0.0").
  - `access_host`: host que usan los clientes para acceder (p.ej. "localhost").
  - `port`: puerto TCP.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Optional, Tuple

import httpx
import typer
import uvicorn
from rich.align import Align
from rich.console import Console
from rich.panel import Panel

from app.config import settings

console = Console()
APP_IMPORT = "app.mcp_aemps_server:app"
DEFAULT_UVICORN_HOST = "0.0.0.0"
DEFAULT_ACCESS_HOST = "localhost"
DEFAULT_PORT = 8000
PID_FILE = Path(".mcp_aemps.pid")
CONFIG_FILE = Path("app/mcp_aemps.json")
DEFAULT_APP_LOG = Path(settings.log_dir) / "mcp_aemps.log"

cli = typer.Typer(add_completion=False, help="CLI del servidor MCP-AEMPS (AEMPS/CIMA)")


def _banner() -> None:
    title_art = """[bold red]███╗   ███╗ ██████╗██████╗      █████╗ ███████╗███╗   ███╗██████╗ ███████╗
████╗ ████║██╔════╝██╔══██╗    ██╔══██╗██╔════╝████╗ ████║██╔══██╗██╔════╝
██╔████╔██║██║     ██████╔╝    ███████║█████╗  ██╔████╔██║██████╔╝███████╗
██║╚██╔╝██║██║     ██╔═══╝     ██╔══██║██╔══╝  ██║╚██╔╝██║██╔═══╝ ╚════██║
██║ ╚═╝ ██║╚██████╗██║         ██║  ██║███████╗██║ ╚═╝ ██║██║     ███████║
╚═╝     ╚═╝ ╚═════╝╚═╝         ╚═╝  ╚═╝╚══════╝╚═╝     ╚═╝╚═╝     ╚══════╝[/bold red]"""
    content = f"""{title_art}

              [bold white]🏥  AGENCIA ESPAÑOLA DE MEDICAMENTOS[/bold white]
                    [bold white]Y PRODUCTOS SANITARIOS[/bold white]

                  [bold white]💊  Centro de Información[/bold white]
                   [bold white]de Medicamentos Autorizados - CIMA[/bold white]"""
    panel = Panel(
        Align.center(content),
        border_style="bright_black",
        padding=(1, 2),
        title="[bold bright_white]Servidor MCP NO OFICIAL de la AEMPS[/bold bright_white]",
        title_align="center",
    )
    console.print("")
    console.print(panel)
    console.print("")

    # Información adicional con enlace clickable
    info_text = (
        "[bold white]La información que devuelve este servidor puedes encontrarla también en:[/bold white]\n"
        "[link=https://cima.aemps.es/cima/publico/home.html]https://cima.aemps.es/cima/publico/home.html[/link]"
    )
    info_panel = Panel(
        Align.center(info_text),
        border_style="bright_black",
        padding=(1, 2),
    )
    console.print(info_panel)
    console.print("")
    console.print(f"[dim]Versión: {settings.mcp_aemps_version}[/dim]", justify="center")
    console.print("")


def _load_config() -> Tuple[str, str, int]:
    """Carga uvicorn_host, access_host y port del fichero de configuración si existe."""
    if CONFIG_FILE.exists():
        try:
            cfg = json.loads(CONFIG_FILE.read_text())
            uvh = cfg.get("uvicorn_host", DEFAULT_UVICORN_HOST)
            acc = cfg.get("access_host", DEFAULT_ACCESS_HOST)
            port = cfg.get("port", DEFAULT_PORT)
            return uvh, acc, port
        except json.JSONDecodeError:
            pass
    return DEFAULT_UVICORN_HOST, DEFAULT_ACCESS_HOST, DEFAULT_PORT


def _save_config(uvicorn_host: str, access_host: str, port: int) -> None:
    data = {}
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text())
        except json.JSONDecodeError:
            pass
    data.update({"uvicorn_host": uvicorn_host, "access_host": access_host, "port": port})

    try:
        tmp = CONFIG_FILE.with_suffix(CONFIG_FILE.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        try:
            os.chmod(tmp, 0o600)
        except Exception:
            pass
        tmp.replace(CONFIG_FILE)  # movimiento atómico en el mismo filesystem
    except Exception:
        console.print("⚠️  No se pudo guardar la configuración en disco.", style="yellow")

def _find_free_port(start_port: int, host: str = DEFAULT_UVICORN_HOST) -> int:
    """
    Intenta bindear al puerto `start_port` en `host`; si está ocupado,
    incrementa hasta encontrar uno libre. Devuelve el puerto libre.
    """
    port = start_port
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            # Evitar errores de TIME_WAIT
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
                return port
            except OSError:
                port += 1

def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False

@cli.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())
        raise typer.Exit()


@cli.command()
def up(
    uvicorn_host: str = typer.Option(
        DEFAULT_UVICORN_HOST, help="Dirección donde bindeará Uvicorn"
    ),
    access_host: str = typer.Option(
        DEFAULT_ACCESS_HOST, help="Host público para acceder a la API"
    ),
    port: int = typer.Option(
        DEFAULT_PORT, help="Puerto TCP"
    ),
    workers: int = typer.Option(
        1, help="Número de workers Uvicorn"
    ),
    log_level: str = typer.Option(
        "info", help="Nivel de log Uvicorn"
    ),
    daemon: bool = typer.Option(
        False, "--daemon/--no-daemon", help="Ejecutar en background"
    ),
    access_log: bool = typer.Option(False, "--access-log/--no-access-log", help="Access log de Uvicorn"),
):
    """Arranca el servidor *sin* autorecarga, orientado a producción."""
    _banner()

    # Comprobar si el puerto está libre; si no, buscar siguiente libre
    puerto_libre = _find_free_port(start_port=port, host=uvicorn_host)
    if puerto_libre != port:
        console.print(
            f"⚠️  El puerto {port} está ocupado; usando puerto libre {puerto_libre}.",
            style="yellow"
        )
        port = puerto_libre

    log_level = log_level.lower()
    cmd = [
        sys.executable, "-m", "uvicorn", APP_IMPORT,
        "--host", uvicorn_host, "--port", str(port),
        "--workers", str(workers),
        "--log-level", log_level,
    ]
    if not access_log:
        cmd.append("--no-access-log")

    # en up(), justo antes de Popen():
    if daemon and PID_FILE.exists():
        try:
            existing = int(PID_FILE.read_text())
            if _pid_alive(existing):
                console.print(f"❌  Ya hay un servidor en ejecución (PID {existing}). Usa `down` o `restart`.", style="red")
                raise typer.Exit(code=1)
        except Exception:
            PID_FILE.unlink(missing_ok=True)

    if daemon:
        log_path = DEFAULT_APP_LOG
        log_path.parent.mkdir(parents=True, exist_ok=True)
        f_out = open(log_path, "a")
        # POSIX
        popen_kwargs = {"start_new_session": True, "stdout": f_out, "stderr": f_out}
        # Windows (opcional):
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore

        proc = subprocess.Popen(cmd, **popen_kwargs)
        f_out.close()
        PID_FILE.write_text(str(proc.pid))
        try:
            os.chmod(PID_FILE, 0o600)
        except Exception:
            pass
        console.print(
            f"🚀  Servidor en marcha (PID [bold]{proc.pid}[/]) → http://{access_host}:{port}",
            style="green",
        )
    else:
        console.print("🏁  Ejecutando servidor en foreground… (Ctrl-C para salir)")
        subprocess.run(cmd, check=False)

    # Guardar configuración final (con el puerto potencialmente ajustado)
    _save_config(uvicorn_host, access_host, port)


@cli.command()
def dev(
    uvicorn_host: str = typer.Option(
        DEFAULT_UVICORN_HOST, help="Host (desarrollo)"
    ),
    access_host: str = typer.Option(
        "localhost", help="Host público para acceder a la API"
    ),
    port: int = typer.Option(DEFAULT_PORT, help="Puerto TCP"),
    access_log: bool = typer.Option(True, "--access-log/--no-access-log", help="Access log de Uvicorn"),
):
    """Arranca el servidor con `--reload` para desarrollo rápido."""
    _banner()

    # Comprobar si el puerto está libre; si no, buscar siguiente libre
    puerto_libre = _find_free_port(start_port=port, host=uvicorn_host)
    if puerto_libre != port:
        console.print(
            f"⚠️  El puerto {port} está ocupado; usando puerto libre {puerto_libre}.",
            style="yellow"
        )
        port = puerto_libre

    console.print("🔄  Modo desarrollo con recarga automática…", style="yellow")
    # Guardar configuración con el puerto utilizado
    _save_config(uvicorn_host, access_host, port)
    uvicorn.run(
        APP_IMPORT,
        host=uvicorn_host,
        port=port,
        reload=True,
        log_level="debug",
        access_log=access_log,  # <- parámetro nativo de uvicorn.run
    )


@cli.command()
def down():
    """Detiene el servidor iniciado con `up --daemon` (lee PID y config)."""
    if not PID_FILE.exists():
        console.print("⚠️  No hay PID registrado; ¿arrancaste con --daemon?", style="yellow")
        raise typer.Exit(code=1)
    pid = int(PID_FILE.read_text())
    console.print(f"🔻  Enviando SIGTERM al proceso {pid}…")
    try:
        try:
            os.killpg(os.getpgid(pid), 15)
        except Exception:
            os.kill(pid, 15)
    except ProcessLookupError:
        console.print("⚠️  Proceso no encontrado; ya estaba parado.", style="yellow")
    finally:
        PID_FILE.unlink(missing_ok=True)
        CONFIG_FILE.unlink(missing_ok=True)


@cli.command()
def status():
    """Comprueba si el servidor está en marcha."""
    if not PID_FILE.exists():
        console.print("❌  No hay servidor en ejecución.", style="red")
        raise typer.Exit(code=1)
    pid = int(PID_FILE.read_text())
    try:
        os.kill(pid, 0)
        uvh, acc, port = _load_config()
        console.print(
            f"✅  Servidor activo (PID {pid}) en http://{acc}:{port}",
            style="green",
        )
    except OSError:
        console.print(f"❌  No se encontró proceso con PID {pid}. ¿Se cerró inesperadamente?", style="red")
        PID_FILE.unlink(missing_ok=True)
        CONFIG_FILE.unlink(missing_ok=True)
        console.print("ℹ️  Puedes arrancar de nuevo con `app cli up --daemon` o `app cli dev`.", style="dim")
        raise typer.Exit(code=1)


@cli.command()
def restart(
    workers: int = typer.Option(2, help="Número de workers Uvicorn"),
    log_level: str = typer.Option("info", help="Nivel de log Uvicorn"),
    daemon: bool = typer.Option(False, "--daemon/--no-daemon", help="Ejecutar en background"),
    uvicorn_host: Optional[str] = None,
    access_host: Optional[str] = None,
    port: Optional[int] = None,
):
    """Reinicia el servidor (down && up) con los mismos parámetros."""
    console.print("🔄  Reiniciando servidor…", style="yellow")
    u, a, p = _load_config()
    uvicorn_host = uvicorn_host or u
    access_host = access_host or a
    port = port or p
    try:
        down()
    except typer.Exit:
        pass
    up(
        uvicorn_host=uvicorn_host,
        access_host=access_host,
        port=port,
        workers=workers,
        log_level=log_level,
        daemon=daemon,
    )


@cli.command()
def logs(
    file: Path = typer.Option(DEFAULT_APP_LOG, exists=False, help="Ruta al archivo de log"),
):
    if not file.exists():
        console.print(f"⚠️  {file} no existe todavía. ¿Se arrancó el server?", style="yellow")
        raise typer.Exit(code=1)
    console.print(f"📜  Mostrando logs desde [bold]{file}[/], Ctrl-C para salir…")
    # Fallback cross-platform si no hay `tail`
    try:
        subprocess.run(["tail", "-f", str(file)])
    except FileNotFoundError:
        import time
        with file.open("r") as f:
            f.seek(0, os.SEEK_END)
            while True:
                line = f.readline()
                if not line:
                    time.sleep(0.25)
                    continue
                sys.stdout.write(line)
                sys.stdout.flush()

@cli.command()
def health(
    access_host: Optional[str] = typer.Option(None, help="Host público para acceder a la API"),
    port: Optional[int] = typer.Option(None, help="Puerto donde se ejecuta la API"),
):
    """Consulta el endpoint /health y muestra el JSON de respuesta."""
    _, acc, p = _load_config()
    host = access_host or acc
    port = port or p
    url = f"http://{host}:{port}/health"
    console.print(f"🔍  Consultando {url}…")
    try:
        resp = httpx.get(url, timeout=5.0)
        resp.raise_for_status()
        console.print(resp.json())
    except Exception as e:
        console.print(f"❌  Error consultando /health: {e}", style="red")
        raise typer.Exit(code=1)


@cli.command()
def openapi(
    output: Path = typer.Option("openapi.json", help="Fichero de salida"),
    access_host: Optional[str] = typer.Option(None, help="Host público"),
    port: Optional[int] = typer.Option(None, help="Puerto API"),
    open_browser: bool = typer.Option(False, help="Abrir en navegador tras descargar"),
):
    """Descarga la especificación OpenAPI, la guarda y abre en navegador."""
    _, acc, p = _load_config()
    host = access_host or acc
    port = port or p
    url = f"http://{host}:{port}/openapi.json"
    console.print(f"📥  Descargando spec desde {url}…")
    try:
        resp = httpx.get(url, timeout=10.0)
        resp.raise_for_status()
        output.write_text(resp.text)
        console.print(f"✅  Spec guardada en [bold]{output}[/].")
        if open_browser:
            file_url = output.resolve().as_uri()
            console.print(f"🌐  Abriendo spec en {file_url}…")
            webbrowser.open(file_url)
    except Exception as e:
        console.print(f"❌  Error descargando o abriendo OpenAPI: {e}", style="red")
        raise typer.Exit(code=1)


@cli.command()
def docs(
    access_host: Optional[str] = typer.Option(None, help="Host público"),
    port: Optional[int] = typer.Option(None, help="Puerto API"),
):
    """Abre la Swagger UI en el navegador."""
    _, acc, p = _load_config()
    host = access_host or acc
    port = port or p
    url = f"http://{host}:{port}/docs"
    console.print(f"🌐  Abriendo docs en {url}…")
    try:
        webbrowser.open(url)
    except Exception as e:
        console.print(f"❌  No se pudo abrir el navegador: {e}", style="red")
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# install / uninstall — auto-config MCP-compatible clients
# ---------------------------------------------------------------------------
install_app = typer.Typer(
    add_completion=False,
    help="Auto-configure mcp-aemps in MCP-compatible clients (Claude Desktop, Claude Code, Codex).",
    invoke_without_command=True,
)
uninstall_app = typer.Typer(
    add_completion=False,
    help="Remove mcp-aemps entry from MCP-compatible clients.",
    invoke_without_command=True,
)
cli.add_typer(install_app, name="install")
cli.add_typer(uninstall_app, name="uninstall")


def _print_install_result(res) -> None:
    icon = {"added": "✅", "updated": "🔄", "unchanged": "ℹ️", "removed": "🗑️"}.get(res.action, "•")
    console.print(f"{icon}  [bold]{res.client}[/]  ({res.action}) — {res.message}")
    console.print(f"    [dim]config: {res.config_path}[/dim]")


@install_app.callback(invoke_without_command=True)
def _install_main(
    ctx: typer.Context,
    url: str = typer.Option("http://localhost:8000/mcp", "--url", help="MCP endpoint URL"),
    name: str = typer.Option("mcp-aemps", "--name", help="Server key in client config"),
):
    """Install in ALL detected clients (default when no subcommand)."""
    if ctx.invoked_subcommand is not None:
        return
    from app.installers import install_claude_code, install_claude_desktop, install_codex

    console.print(f"🔌  Installing [bold]mcp-aemps[/] (key=[cyan]{name}[/], url=[cyan]{url}[/])\n")
    for installer in (install_claude_desktop, install_claude_code, install_codex):
        try:
            res = installer(url=url, server_key=name)
            _print_install_result(res)
        except Exception as exc:
            console.print(f"❌  {installer.__name__}: {type(exc).__name__}: {exc}", style="red")
    console.print("\n[dim]Restart the affected clients to pick up the change.[/dim]")


@install_app.command("claude-desktop")
def _install_claude_desktop(
    url: str = typer.Option("http://localhost:8000/mcp", "--url"),
    name: str = typer.Option("mcp-aemps", "--name"),
):
    """Install in Claude Desktop only."""
    from app.installers import install_claude_desktop
    _print_install_result(install_claude_desktop(url=url, server_key=name))


@install_app.command("claude-code")
def _install_claude_code(
    url: str = typer.Option("http://localhost:8000/mcp", "--url"),
    name: str = typer.Option("mcp-aemps", "--name"),
    scope: str = typer.Option("user", "--scope", help="Claude Code scope: user | project | local"),
):
    """Install in Claude Code only (uses `claude mcp add` if available)."""
    from app.installers import install_claude_code
    _print_install_result(install_claude_code(url=url, server_key=name, scope=scope))


@install_app.command("codex")
def _install_codex(
    url: str = typer.Option("http://localhost:8000/mcp", "--url"),
    name: str = typer.Option("mcp-aemps", "--name"),
):
    """Install in OpenAI Codex CLI only."""
    from app.installers import install_codex
    _print_install_result(install_codex(url=url, server_key=name))


@uninstall_app.callback(invoke_without_command=True)
def _uninstall_main(
    ctx: typer.Context,
    name: str = typer.Option("mcp-aemps", "--name", help="Server key to remove"),
):
    """Uninstall from ALL detected clients (default when no subcommand)."""
    if ctx.invoked_subcommand is not None:
        return
    from app.installers import uninstall_claude_code, uninstall_claude_desktop

    console.print(f"🧹  Removing [bold]{name}[/] from MCP clients\n")
    for u in (uninstall_claude_desktop, uninstall_claude_code):
        try:
            _print_install_result(u(server_key=name))
        except Exception as exc:
            console.print(f"❌  {u.__name__}: {type(exc).__name__}: {exc}", style="red")


@uninstall_app.command("claude-desktop")
def _uninstall_claude_desktop(name: str = typer.Option("mcp-aemps", "--name")):
    """Remove from Claude Desktop only."""
    from app.installers import uninstall_claude_desktop
    _print_install_result(uninstall_claude_desktop(server_key=name))


@uninstall_app.command("claude-code")
def _uninstall_claude_code(name: str = typer.Option("mcp-aemps", "--name")):
    """Remove from Claude Code only."""
    from app.installers import uninstall_claude_code
    _print_install_result(uninstall_claude_code(server_key=name))


if __name__ == "__main__":
    cli()
