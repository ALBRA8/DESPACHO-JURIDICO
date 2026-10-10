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
    import time

    from albra.comms.base import ChannelMessage
    from albra.identity.agent import get_agent
    agent = get_agent()
    click.echo(f"\n{AGENT_MANIFEST.name} v{AGENT_MANIFEST.version}")
    click.echo("Escribe 'salir' para terminar.\n")

    async def _run() -> None:
        await agent.boot()
        comms = agent.organs["comms"]

        async def handler(message):
            r = await agent.process(message.text, channel=message.channel, user=message.user)
            return r["reply"]

        comms.set_agent_handler(handler)
        while True:
            try:
                msg = click.prompt(">", type=str)
            except (click.exceptions.Abort, EOFError):
                break
            if msg.strip().lower() in ("salir", "exit", "quit"):
                break
            cm = ChannelMessage(channel="text", user="cli_user", text=msg, ts=time.time())
            result = await comms.route_in(cm)
            click.echo(f"\n[ALBRA] {result['reply']}\n")
        await agent.shutdown()

    asyncio.run(_run())


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
            click.echo(f"  - {t['name']:22s} risk={t['risk']:6s} cat={t['category']:8s} → {t['description']}")
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
def firewall() -> None:
    """Lista las políticas del Action Firewall."""
    from albra.security.firewall.policy import FIREWALL_POLICIES
    click.echo("Políticas del Action Firewall:")
    for name, p in FIREWALL_POLICIES.items():
        click.echo(f"  - {name:30s} risk={p.risk:8s} hitl={p.requires_hitl}")
    click.echo(f"\nTotal: {len(FIREWALL_POLICIES)} políticas")


@main.command()
def policies() -> None:
    """Lista las políticas declarativas (Policy-as-Code)."""
    from albra.security.policy import PolicyEngine
    eng = PolicyEngine()
    for p in eng.list():
        click.echo(f"  - [{p['id']:12s}] {p['name']:35s} rule: {p['rule']:40s} action: {p['action']}")


@main.command()
def manifests() -> None:
    """Lista los manifests de los órganos (role/goal/backstory)."""
    from albra.identity.organ_manifests import list_organ_manifests
    for m in list_organ_manifests():
        click.echo(f"\n[{m['name']}]")
        click.echo(f"  Role: {m['role']}")
        click.echo(f"  Goal: {m['goal']}")
        click.echo(f"  Backstory: {m['backstory']}")


@main.command()
def sops() -> None:
    """Lista los SOPs jurídicos disponibles."""
    from albra.workflows.sops import list_sops
    click.echo("SOPs jurídicos disponibles:")
    for s in list_sops():
        click.echo(f"  - {s['name']:30s} steps={s['steps_count']} hitl_steps={s['hitl_steps']} "
                   f"≈{s['estimated_total_minutes']}min total")


@main.command()
def jurisdictions() -> None:
    """Lista las jurisdicciones soportadas en el catálogo MCP."""
    from albra.mcp.jurisdictions import JurisdictionCatalog
    cat = JurisdictionCatalog()
    click.echo("Catálogo MCP multi-jurisdicción:")
    for j in cat.list():
        click.echo(f"  - {j['jurisdiction']:5s} {j['name']:25s} url={j['url']} - {j['description']}")


@main.command()
def debate() -> None:
    """Demo del debate adversarial."""
    from albra.reasoning.debate import AdversarialDebate

    async def _run() -> None:
        click.echo("Escribí una pregunta jurídica para el debate:")
        q = click.prompt("Pregunta", type=str)
        debate = AdversarialDebate(get_agent_settings(), provider=None)
        result = await debate.run_debate(q)
        for arg in result.arguments:
            click.echo(f"\n[{arg.role}]")
            click.echo(arg.argument)
        click.echo("\n[MAGISTRADO - Dictamen]")
        click.echo(result.ruling)

    asyncio.run(_run())


@main.command()
def audit_verify() -> None:
    """Verifica la integridad del audit log con hash chain."""
    from albra.audit.tamper_evident import TamperEvidentAudit
    from albra.config.settings import Settings
    s = Settings()
    audit = TamperEvidentAudit(s.audit_path)
    result = audit.verify_chain()
    click.echo(json.dumps(result, indent=2))
    click.echo(f"\nFingerprint actual: {audit.fingerprint()}")


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


def get_agent_settings():
    from albra.config.settings import Settings
    return Settings()


if __name__ == "__main__":
    main()
