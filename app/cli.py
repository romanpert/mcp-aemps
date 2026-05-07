# app/cli.py
"""mcp-aemps CLI — start/stop/install/uninstall the MCP AEMPS server.

Commands
--------
- up / dev / down / restart / status / logs / health / openapi / docs
- install / uninstall (with subcommands per client)

The CLI writes the actually-bound host:port to a per-user runtime file so
`mcp-aemps install` can pick it up automatically — install once, change
the port later, and clients keep working without re-installing.
"""

from __future__ import annotations

import os
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Optional

import httpx
import typer
import uvicorn
from rich.align import Align
from rich.console import Console
from rich.panel import Panel

from app.config import settings
from app.runtime_state import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    clear_runtime,
    find_free_port,
    read_runtime,
    state_dir,
    write_runtime,
)
from app.runtime_state import (
    PATH as MCP_PATH,
)

console = Console()
APP_IMPORT = "app.mcp_aemps_server:app"
PID_FILE = state_dir() / "mcp_aemps.pid"

DEFAULT_UVICORN_HOST = "0.0.0.0"
DEFAULT_ACCESS_HOST = DEFAULT_HOST

cli = typer.Typer(add_completion=False, help="CLI del servidor MCP-AEMPS (AEMPS/CIMA)")


# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------
def _banner() -> None:
    body = (
        "[bold red]MCP AEMPS · CIMA[/bold red]\n\n"
        "[bold white]🏥  Servidor MCP NO OFICIAL para la AEMPS[/bold white]\n"
        "[dim]Datos: https://cima.aemps.es/cima/publico/home.html[/dim]\n\n"
        f"[dim]Versión: {settings.mcp_aemps_version}[/dim]"
    )
    console.print("")
    console.print(Panel(Align.center(body), border_style="bright_black", padding=(1, 2)))
    console.print("")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _ensure_state_dir() -> None:
    state_dir().mkdir(parents=True, exist_ok=True)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _resolve_port(requested: int, *, auto: bool, bind_host: str) -> int:
    if not auto:
        return requested
    free = find_free_port(start=requested, host=bind_host)
    if free != requested:
        console.print(f"⚠️  Puerto {requested} ocupado; usando libre {free}.", style="yellow")
    return free


@cli.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())
        raise typer.Exit()


# ---------------------------------------------------------------------------
# Lifecycle commands
# ---------------------------------------------------------------------------
@cli.command()
def up(
    uvicorn_host: str = typer.Option(DEFAULT_UVICORN_HOST, help="Bind host"),
    access_host: str = typer.Option(DEFAULT_ACCESS_HOST, help="Public host clients connect to"),
    port: int = typer.Option(DEFAULT_PORT, help=f"TCP port (default {DEFAULT_PORT})"),
    workers: int = typer.Option(1, help="Uvicorn worker count"),
    log_level: str = typer.Option("info", help="Uvicorn log level"),
    daemon: bool = typer.Option(False, "--daemon/--no-daemon", help="Run in background"),
    access_log: bool = typer.Option(False, "--access-log/--no-access-log"),
    auto_port: bool = typer.Option(True, "--auto-port/--no-auto-port"),
):
    """Start the server (production mode, no autoreload)."""
    _banner()
    _ensure_state_dir()

    actual_port = _resolve_port(port, auto=auto_port, bind_host=uvicorn_host)
    write_runtime(host=access_host, port=actual_port)

    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        APP_IMPORT,
        "--host",
        uvicorn_host,
        "--port",
        str(actual_port),
        "--workers",
        str(workers),
        "--log-level",
        log_level.lower(),
    ]
    if not access_log:
        cmd.append("--no-access-log")

    if daemon and PID_FILE.exists():
        try:
            existing = int(PID_FILE.read_text())
            if _pid_alive(existing):
                console.print(
                    f"❌  Ya hay un servidor activo (PID {existing}). Usa `down` o `restart`.",
                    style="red",
                )
                raise typer.Exit(code=1)
        except Exception:
            PID_FILE.unlink(missing_ok=True)

    if daemon:
        log_path = Path(settings.log_dir) / "mcp_aemps.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        f_out = open(log_path, "a")
        popen_kwargs: dict = {"start_new_session": True, "stdout": f_out, "stderr": f_out}
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]

        proc = subprocess.Popen(cmd, **popen_kwargs)
        f_out.close()
        PID_FILE.write_text(str(proc.pid))
        try:
            os.chmod(PID_FILE, 0o600)
        except OSError:
            pass
        write_runtime(host=access_host, port=actual_port, pid=proc.pid)
        console.print(
            f"🚀  Servidor en marcha (PID {proc.pid}) → http://{access_host}:{actual_port}{MCP_PATH}",
            style="green",
        )
    else:
        console.print(f"🏁  Foreground en http://{access_host}:{actual_port}{MCP_PATH} (Ctrl-C para salir)")
        subprocess.run(cmd, check=False)


@cli.command()
def dev(
    uvicorn_host: str = typer.Option(DEFAULT_UVICORN_HOST, help="Bind host (dev)"),
    access_host: str = typer.Option(DEFAULT_ACCESS_HOST, help="Public host"),
    port: int = typer.Option(DEFAULT_PORT, help=f"TCP port (default {DEFAULT_PORT})"),
    access_log: bool = typer.Option(True, "--access-log/--no-access-log"),
    auto_port: bool = typer.Option(True, "--auto-port/--no-auto-port"),
):
    """Start the server with --reload for development."""
    _banner()
    _ensure_state_dir()
    actual_port = _resolve_port(port, auto=auto_port, bind_host=uvicorn_host)
    write_runtime(host=access_host, port=actual_port)
    console.print("🔄  Modo desarrollo (autorecarga)…", style="yellow")
    uvicorn.run(
        APP_IMPORT,
        host=uvicorn_host,
        port=actual_port,
        reload=True,
        log_level="debug",
        access_log=access_log,
    )


@cli.command()
def down():
    """Stop a daemon-started server."""
    if not PID_FILE.exists():
        console.print("⚠️  No hay PID registrado.", style="yellow")
        raise typer.Exit(code=1)
    pid = int(PID_FILE.read_text())
    console.print(f"🔻  SIGTERM al PID {pid}…")
    try:
        try:
            os.killpg(os.getpgid(pid), 15)
        except (AttributeError, OSError):
            os.kill(pid, 15)
    except ProcessLookupError:
        console.print("⚠️  Proceso ya parado.", style="yellow")
    finally:
        PID_FILE.unlink(missing_ok=True)
        clear_runtime()


@cli.command()
def status():
    """Check whether the server is running."""
    if not PID_FILE.exists():
        console.print("❌  No hay servidor en ejecución.", style="red")
        raise typer.Exit(code=1)
    pid = int(PID_FILE.read_text())
    try:
        os.kill(pid, 0)
        rt = read_runtime() or {}
        host = rt.get("host", DEFAULT_HOST)
        port = rt.get("port", DEFAULT_PORT)
        console.print(
            f"✅  Servidor activo (PID {pid}) en http://{host}:{port}{MCP_PATH}",
            style="green",
        )
    except OSError:
        console.print(f"❌  PID {pid} no responde.", style="red")
        PID_FILE.unlink(missing_ok=True)
        clear_runtime()
        raise typer.Exit(code=1)


@cli.command()
def restart(
    workers: int = typer.Option(2),
    log_level: str = typer.Option("info"),
    daemon: bool = typer.Option(False, "--daemon/--no-daemon"),
):
    """Stop and start again (preserves last bound host/port)."""
    rt = read_runtime() or {}
    host = rt.get("host", DEFAULT_HOST)
    port = rt.get("port", DEFAULT_PORT)
    try:
        down()
    except typer.Exit:
        pass
    up(
        uvicorn_host=DEFAULT_UVICORN_HOST,
        access_host=host,
        port=port,
        workers=workers,
        log_level=log_level,
        daemon=daemon,
    )


@cli.command()
def logs(
    file: Path = typer.Option(Path(settings.log_dir) / "mcp_aemps.log", help="Log file path"),
):
    """Tail the server log."""
    if not file.exists():
        console.print(f"⚠️  {file} no existe todavía.", style="yellow")
        raise typer.Exit(code=1)
    console.print(f"📜  {file} (Ctrl-C para salir)…")
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


def _resolve_health_base(access_host: Optional[str], port: Optional[int]) -> str:
    rt = read_runtime() or {}
    host = access_host or rt.get("host", DEFAULT_HOST)
    p = port or rt.get("port", DEFAULT_PORT)
    return f"http://{host}:{p}"


@cli.command()
def health(
    access_host: Optional[str] = typer.Option(None),
    port: Optional[int] = typer.Option(None),
):
    """Hit /health and show the JSON response."""
    url = f"{_resolve_health_base(access_host, port)}/health"
    console.print(f"🔍  GET {url}")
    try:
        resp = httpx.get(url, timeout=5.0)
        resp.raise_for_status()
        console.print(resp.json())
    except Exception as e:
        console.print(f"❌  {e}", style="red")
        raise typer.Exit(code=1)


@cli.command()
def openapi(
    output: Path = typer.Option(Path("openapi.json")),
    access_host: Optional[str] = typer.Option(None),
    port: Optional[int] = typer.Option(None),
    open_browser: bool = typer.Option(False),
):
    """Download the OpenAPI spec."""
    url = f"{_resolve_health_base(access_host, port)}/openapi.json"
    console.print(f"📥  {url}")
    try:
        resp = httpx.get(url, timeout=10.0)
        resp.raise_for_status()
        output.write_text(resp.text)
        console.print(f"✅  Saved to {output}.")
        if open_browser:
            webbrowser.open(output.resolve().as_uri())
    except Exception as e:
        console.print(f"❌  {e}", style="red")
        raise typer.Exit(code=1)


@cli.command()
def stdio():
    """Run as a native stdio MCP server (Anthropic-canonical pattern).

    Use this when a client like Claude Desktop or Codex is configured to
    launch the server itself:

        {"command": "uvx", "args": ["mcp-aemps", "stdio"]}

    No HTTP server is started; the process talks JSON-RPC over
    stdin/stdout and exits when the client closes the connection.
    """
    from app.stdio_server import main as stdio_main

    stdio_main()


@cli.command()
def docs(
    access_host: Optional[str] = typer.Option(None),
    port: Optional[int] = typer.Option(None),
):
    """Open Swagger UI in the browser."""
    url = f"{_resolve_health_base(access_host, port)}/docs"
    console.print(f"🌐  {url}")
    try:
        webbrowser.open(url)
    except Exception as e:
        console.print(f"❌  {e}", style="red")
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# install / uninstall
# ---------------------------------------------------------------------------
install_app = typer.Typer(
    add_completion=False,
    help="Auto-configure mcp-aemps in MCP-compatible clients.",
    invoke_without_command=True,
)
uninstall_app = typer.Typer(
    add_completion=False,
    help="Remove mcp-aemps entry from MCP-compatible clients.",
    invoke_without_command=True,
)
cli.add_typer(install_app, name="install")
cli.add_typer(uninstall_app, name="uninstall")

_INSTALL_ICONS = {"added": "✅", "updated": "🔄", "unchanged": "ℹ️", "removed": "🗑️"}


def _print_install_result(res) -> None:
    icon = _INSTALL_ICONS.get(res.action, "•")

    # UX rule (v0.4.12): print client-detection status FIRST so the user
    # reads "is the IDE installed?" before "did we configure it?". The
    # detection NOTEs come from _check_client_installed in the installer
    # and use the prefix "NOTE:". Pre-v0.4.12 we printed the install
    # action first and the detection NOTE last as a footer — that order
    # made users assume the install succeeded when in fact the client
    # wasn't even on the machine.
    warnings = getattr(res, "warnings", ()) or ()
    detection_note = next(
        (w for w in warnings if w.startswith("NOTE:") and "doesn't appear to be installed" in w),
        None,
    )
    other_warnings = [w for w in warnings if w is not detection_note]

    if detection_note is not None:
        console.print(f"🔍  [bold]{res.client}[/] · [yellow]not detected[/]")
        console.print(f"    [yellow]{detection_note}[/yellow]")
    else:
        console.print(f"🔍  [bold]{res.client}[/] · [green]detected[/]")

    console.print(f"{icon}  [bold]{res.client}[/]  ({res.action}) — {res.message}")
    console.print(f"    [dim]config: {res.config_path}[/dim]")

    for warning in other_warnings:
        style = "yellow" if warning.startswith("WARNING") else "cyan"
        console.print(f"    [{style}]{warning}[/{style}]")


@install_app.callback(invoke_without_command=True)
def _install_main(
    ctx: typer.Context,
    url: Optional[str] = typer.Option(
        None,
        "--url",
        help=f"MCP endpoint URL (default: from runtime file, else http://{DEFAULT_HOST}:{DEFAULT_PORT}{MCP_PATH})",
    ),
    name: str = typer.Option("mcp-aemps", "--name", help="Server key in client config"),
):
    """Install in ALL detected clients (default when no subcommand)."""
    if ctx.invoked_subcommand is not None:
        return
    from app.installers import ALL_INSTALLERS

    console.print(f"🔌  Installing [bold]mcp-aemps[/] (key=[cyan]{name}[/])\n")
    for client_name, fn in ALL_INSTALLERS.items():
        try:
            kwargs = {"server_key": name}
            if url is not None:
                kwargs["url"] = url
            res = fn(**kwargs)
            _print_install_result(res)
        except Exception as exc:
            console.print(f"❌  {client_name}: {type(exc).__name__}: {exc}", style="red")
    console.print("\n[dim]Restart the affected clients to pick up the change.[/dim]")


def _make_install_cmd(helper):
    def _cmd(
        url: Optional[str] = typer.Option(None, "--url"),
        name: str = typer.Option("mcp-aemps", "--name"),
    ):
        kwargs = {"server_key": name}
        if url is not None:
            kwargs["url"] = url
        _print_install_result(helper(**kwargs))

    return _cmd


def _make_uninstall_cmd(helper):
    def _cmd(name: str = typer.Option("mcp-aemps", "--name")):
        _print_install_result(helper(server_key=name))

    return _cmd


def _register_install_subcommands() -> None:
    from app.installers import ALL_INSTALLERS, ALL_UNINSTALLERS

    for client_key, helper in ALL_INSTALLERS.items():
        install_app.command(client_key, help=f"Install in {client_key} only.")(_make_install_cmd(helper))
    for client_key, helper in ALL_UNINSTALLERS.items():
        uninstall_app.command(client_key, help=f"Remove from {client_key} only.")(_make_uninstall_cmd(helper))


_register_install_subcommands()


@uninstall_app.callback(invoke_without_command=True)
def _uninstall_main(
    ctx: typer.Context,
    name: str = typer.Option("mcp-aemps", "--name"),
):
    """Uninstall from ALL detected clients (default when no subcommand)."""
    if ctx.invoked_subcommand is not None:
        return
    from app.installers import ALL_UNINSTALLERS

    console.print(f"🧹  Removing [bold]{name}[/] from MCP clients\n")
    for client_name, fn in ALL_UNINSTALLERS.items():
        try:
            _print_install_result(fn(server_key=name))
        except Exception as exc:
            console.print(f"❌  {client_name}: {type(exc).__name__}: {exc}", style="red")


if __name__ == "__main__":
    cli()
