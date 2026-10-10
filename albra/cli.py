"""CLI ALBRA - línea de comandos."""
from __future__ import annotations

import asyncio
import json
import sys

import click

from albra.identity.manifest import AGENT_MANIFEST


@click.group()
@click.version_option(AGENT_MANIFEST.version)
def main() -> None:
    """ALBRA - DESPACHO JURÍDICO DIGITAL - CLI"""


@main.command()
def info() -> None:
    """Muestra la identidad del agente."""
    click.echo(json.dumps(AGENT_MANIFEST.manifest(), indent=2, ensure_ascii=False))


@main.command()
def chat() -> None:
    """Modo conversacional por terminal."""
    from albra.identity.agent import get_agent
    agent = get_agent()
    click.echo(f"\n{AGENT_MANIFEST.name} v{AGENT_MANIFEST.version}")
    click.echo("Escribe 'salir' para terminar.\n")

    async def _run() -> None:
        await agent.boot()
        # Wire comms
        text_adapter = agent.organs["comms"]._adapters.get("text")
        async def handler(message):
            r = await agent.process(message.text, channel=message.channel, user=message.user)
            return r["reply"]
        agent.organs["comms"].set_agent_handler(handler)
        while True:
            try:
                msg = click.prompt(">", type=str)
            except (click.exceptions.Abort, EOFError):
                break
            if msg.strip().lower() in ("salir", "exit", "quit"):
                break
            text_adapter.push_from_stdin("cli_user", msg)
            await agent.organs["comms"].route_in(
                type(text_adapter)._class_call(msg) if False else _make_msg("text", "cli_user", msg)
            )
        await agent.shutdown()

    asyncio.run(_run())


def _make_msg(channel: str, user: str, text: str):
    import time
    from albra.comms.base import ChannelMessage
    return ChannelMessage(channel=channel, user=user, text=text, ts=time.time())


@main.command()
def doctor() -> None:
    """Diagnóstico completo del agente."""
    from albra.identity.agent import get_agent

    async def _run() -> None:
        agent = get_agent()
        await agent.boot()
        doc = agent.organs["doctor"]
        report = await doc.diagnose(scope="all")
        click.echo(json.dumps(report.as_dict(), indent=2, ensure_ascii=False, default=str))
        await agent.shutdown()

    asyncio.run(_run())


@main.command()
def organs() -> None:
    """Lista los órganos activos."""
    from albra.identity.agent import get_agent

    async def _run() -> None:
        agent = get_agent()
        await agent.boot()
        click.echo("Órganos inicializados:")
        for name, organ in agent.organs.items():
            cls = type(organ).__name__
            click.echo(f"  - {name:15s} → {cls}")
        await agent.shutdown()

    asyncio.run(_run())


@main.command()
def capabilities() -> None:
    """Lista las capacidades del agente."""
    from albra.identity.agent import get_agent

    async def _run() -> None:
        agent = get_agent()
        await agent.boot()
        caps = agent.organs["capabilities"]
        click.echo("Capacidades ACTIVE:")
        for c in caps.list_active():
            click.echo(f"  - {c['name']}: {c['description']}")
        click.echo("\nCapacidades PREPARED (requieren configuración):")
        for c in caps.list_prepared():
            click.echo(f"  - {c['name']}: {c['description']}")
        await agent.shutdown()

    asyncio.run(_run())


@main.command()
def tools() -> None:
    """Lista las herramientas registradas."""
    from albra.identity.agent import get_agent

    async def _run() -> None:
        agent = get_agent()
        await agent.boot()
        tr = agent.organs["tools"]
        for t in tr.list():
            click.echo(f"  - {t['name']:18s} risk={t['risk']:6s} cat={t['category']:8s} → {t['description']}")
        await agent.shutdown()

    asyncio.run(_run())


@main.command()
def memory() -> None:
    """Estadísticas de memoria."""
    from albra.identity.agent import get_agent

    async def _run() -> None:
        agent = get_agent()
        await agent.boot()
        mem = agent.organs["memory"]
        click.echo(json.dumps(mem.stats(), indent=2, ensure_ascii=False, default=str))
        await agent.shutdown()

    asyncio.run(_run())


@main.command()
def serve() -> None:
    """Inicia API HTTP (si fastapi está instalado)."""
    try:
        import uvicorn  # type: ignore[import]
    except ImportError:
        click.echo("uvicorn no instalado. Instala con: pip install albra-despacho-juridico[server]")
        sys.exit(1)
    from albra.api.app import app
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
