"""CLI ALBRA - línea de comandos."""
from __future__ import annotations

import asyncio
import json
import os
import sys

import click

from albra.identity.manifest import AGENT_MANIFEST


# ===== V5.1: CLI local-only guard =====
# The CLI commands that read or modify matter/pending-action data call
# MatterStore directly, without going through McpServer.call_tool. That
# means they bypass AuthContext propagation and tenant_id enforcement.
#
# For local development this is fine and is the documented contract. For
# production deployments it is NOT acceptable: a CLI command run on the
# host where ALBRA_ENVIRONMENT=production must never touch the production
# MatterStore without an explicit, auditable override.
#
# The guard works as follows:
#   * If ALBRA_ENVIRONMENT=production AND ALBRA_CLI_ALLOW_LOCAL != "1":
#       The data-touching command refuses to run and prints a clear error.
#   * ALBRA_CLI_ALLOW_LOCAL=1 is the explicit escape hatch. Setting it
#     requires an operator with shell access to the production host, and
#     its use should be audited via external logging (e.g. ssh session
#     recording, sudo logs).
#
# Commands that do NOT touch tenant data (info, agent list, research) are
# not guarded. They are read-only on tenant-agnostic shared resources
# (manifest, organigrama, citation corpus).
def _enforce_local_only(command_name: str) -> None:
    """Refuse to run data-touching CLI commands under production settings.

    V5.1 HARDENING: closes the CLI bypass identified in V5.0.
    Previously the CLI was *documented* as LOCAL_ONLY but the code did
    nothing to enforce it. Now it does.
    """
    try:
        from albra.config.settings import Settings
        settings = Settings()
    except Exception:  # noqa: BLE001
        # If Settings itself fails (e.g. insecure secrets), let the
        # command itself surface the error. The guard is a safety net,
        # not a substitute for proper configuration.
        return
    if not settings.is_production():
        return
    if os.environ.get("ALBRA_CLI_ALLOW_LOCAL") == "1":
        return
    click.echo(
        f"REFUSED: '{command_name}' is a local-only command and cannot run "
        f"in production (ALBRA_ENVIRONMENT=production). Production data "
        f"access must go through the MCP HTTP API with bearer-token "
        f"authentication. To override, set ALBRA_CLI_ALLOW_LOCAL=1 (this "
        f"should be audited and only used for emergency recovery).",
        err=True,
    )
    sys.exit(2)


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


# ============================================================
# V2.0 — Despacho Jurídico (Matters, Agents, Pending, Audit)
# ============================================================


@main.group()
def matter() -> None:
    """Gestión de matters (expedientes digitales) V2.0."""


@matter.command("new")
@click.option("--client", required=True, help="Nombre del cliente")
@click.option("--area", required=True,
              type=click.Choice([
                  "civil", "constitucional", "laboral", "penal",
                  "corporativo", "administrativo", "familia"
              ]),
              help="Área de práctica")
@click.option("--parties", default="", help="Lista separada por comas")
@click.option("--created-by", default="cli", help="Usuario que crea")
def matter_new(client, area, parties, created_by):
    """Crea un matter nuevo (state=NUEVO)."""
    _enforce_local_only("matter new")
    from albra.config.settings import Settings
    from albra.matters.store import MatterStore
    from albra.matters.timeline import MatterTimeline
    s = Settings()
    store = MatterStore(s.matter_db_path)
    timeline = MatterTimeline(s.matter_data_dir)
    party_list = [p.strip() for p in parties.split(",") if p.strip()] if parties else []
    m = store.create_matter(
        client=client, area=area, parties=party_list, created_by=created_by,
    )
    timeline.append(m.id, actor=created_by, event_type="created",
                    description=f"Matter creado para {client} ({area})")
    click.echo(f"Matter created: {m.id}")
    click.echo(f"  client: {m.client}")
    click.echo(f"  area:   {m.area}")
    click.echo(f"  state:  {m.state}")
    click.echo(f"  parties: {m.parties}")
    store.close()


@matter.command("list")
@click.option("--status", default=None, help="Filtrar por estado")
@click.option("--area", default=None, help="Filtrar por área")
@click.option("--client", default=None, help="Filtrar por cliente (substring)")
def matter_list(status, area, client):
    """Lista matters (filtros opcionales)."""
    _enforce_local_only("matter list")
    from albra.config.settings import Settings
    from albra.matters.store import MatterStore
    s = Settings()
    store = MatterStore(s.matter_db_path)
    matters = store.list_matters(state=status, area=area, client=client)
    if not matters:
        click.echo("No matters found.")
        return
    click.echo(f"{'ID':<34} {'CLIENT':<25} {'AREA':<15} {'STATE':<28}")
    click.echo("-" * 110)
    for m in matters:
        click.echo(f"{m.id:<34} {m.client[:25]:<25} {m.area:<15} {m.state:<28}")
    click.echo(f"\nTotal: {len(matters)} matter(s)")
    store.close()


@matter.command("show")
@click.argument("matter_id")
def matter_show(matter_id):
    """Muestra detalle de un matter."""
    _enforce_local_only("matter show")
    from albra.config.settings import Settings
    from albra.matters.store import MatterStore
    s = Settings()
    store = MatterStore(s.matter_db_path)
    m = store.get_matter(matter_id)
    if not m:
        click.echo(f"Matter not found: {matter_id}")
        sys.exit(1)
    click.echo(json.dumps(m.as_dict(), indent=2, ensure_ascii=False, default=str))
    store.close()


@matter.command("advance")
@click.argument("matter_id")
@click.argument("target")
@click.option("--by", default="cli", help="Usuario que avanza")
@click.option("--reason", default="", help="Razón de la transición")
def matter_advance(matter_id, target, by, reason):
    """Avanza el state machine del matter (monótono)."""
    _enforce_local_only("matter advance")
    from albra.config.settings import Settings
    from albra.matters.store import MatterStore
    from albra.matters.timeline import MatterTimeline
    s = Settings()
    store = MatterStore(s.matter_db_path)
    timeline = MatterTimeline(s.matter_data_dir)
    try:
        m = store.advance_state(matter_id, target, by=by, reason=reason)
        timeline.append(m.id, actor=by, event_type="state_change",
                        description=f"→ {target}: {reason or 'manual'}")
        click.echo(f"Matter advanced: {m.id} → {m.state}")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    store.close()


@matter.command("timeline")
@click.argument("matter_id")
def matter_timeline(matter_id):
    """Muestra el timeline.jsonl del matter."""
    _enforce_local_only("matter timeline")
    from albra.config.settings import Settings
    from albra.matters.timeline import MatterTimeline
    s = Settings()
    timeline = MatterTimeline(s.matter_data_dir)
    events = timeline.read(matter_id)
    if not events:
        click.echo(f"No timeline events for matter: {matter_id}")
        return
    click.echo(f"Timeline for matter {matter_id} ({len(events)} events):")
    click.echo()
    for e in events:
        click.echo(f"[{e['ts']}] {e['actor']:15s} {e['event_type']:15s} {e['description']}")


@matter.command("audit")
@click.argument("matter_id")
def matter_audit(matter_id):
    """Verifica el hash chain del audit log del matter."""
    _enforce_local_only("matter audit")
    from albra.audit.matter_audit import MatterAudit
    from albra.config.settings import Settings
    s = Settings()
    audit = MatterAudit(s.matter_data_dir)
    result = audit.verify_chain(matter_id)
    click.echo(json.dumps(result, indent=2))
    if result["ok"]:
        click.echo(f"\n✓ Hash chain verified: {result['total']} entries, no tampering detected.")
    else:
        click.echo(f"\n✗ Hash chain BROKEN at entries: {result['broken_at']}", err=True)
        click.echo("  Audit trail tampering detected.", err=True)
    click.echo(f"\nFingerprint: {audit.fingerprint(matter_id)}")


@main.group()
def agent() -> None:
    """Gestión del organigrama de agentes V2.0."""


@agent.command("list")
def agent_list():
    """Lista los agentes del organigrama."""
    from albra.agents.loader import AgentLoader
    loader = AgentLoader()
    agents = loader.load_all()
    if not agents:
        click.echo("No agents loaded.")
        return
    click.echo(f"{'ID':<18} {'NAME':<18} {'TIER':<12} {'REPORTS_TO':<18} {'SIGNOFF'}")
    click.echo("-" * 80)
    for a in sorted(agents.values(), key=lambda x: x.id):
        click.echo(f"{a.id:<18} {a.name:<18} {a.tier:<12} {a.reports_to:<18} {a.minimum_human_signoff}")
    click.echo(f"\nTotal: {len(agents)} agents")


@agent.command("show")
@click.argument("agent_id")
def agent_show(agent_id):
    """Muestra un agente (markdown + YAML frontmatter)."""
    from albra.agents.loader import AgentLoader
    loader = AgentLoader()
    a = loader.get(agent_id)
    if not a:
        click.echo(f"Agent not found: {agent_id}")
        sys.exit(1)
    click.echo(json.dumps(a.as_dict(), indent=2, ensure_ascii=False, default=str))


@agent.command("reload")
def agent_reload():
    """Recarga definiciones desde disco."""
    from albra.agents.loader import AgentLoader
    loader = AgentLoader()
    agents = loader.reload()
    click.echo(f"Reloaded {len(agents)} agents: {sorted(agents.keys())}")


@main.group(name="pending")
def pending_group() -> None:
    """Acciones pendientes de aprobación (AWAITING-PARTNER) V2.0."""


@pending_group.command("list")
@click.option("--matter", default=None, help="Filtrar por matter_id")
def pending_list(matter):
    """Lista acciones pendientes de aprobación."""
    _enforce_local_only("pending list")
    from albra.config.settings import Settings
    from albra.matters.store import MatterStore
    s = Settings()
    store = MatterStore(s.matter_db_path)
    pending = store.list_pending(matter_id=matter)
    if not pending:
        click.echo("No pending actions.")
        return
    click.echo(f"{'ID':<34} {'MATTER':<34} {'TYPE':<25} {'SIGNOFF'}")
    click.echo("-" * 100)
    for a in pending:
        click.echo(f"{a['id']:<34} {a['matter_id']:<34} {a['action_type']:<25} "
                   f"{len(a['approvals'])}/{a['minimum_human_signoff']}")
    click.echo(f"\nTotal: {len(pending)} pending action(s)")
    store.close()


@pending_group.command("approve")
@click.argument("action_id")
@click.option("--by", required=True, help="Usuario que firma")
@click.option("--role", required=True,
              type=click.Choice(["paralegal", "abogado", "socio", "cliente"]),
              help="Rol del firmante")
@click.option("--comment", default="", help="Comentario de la firma")
def pending_approve(action_id, by, role, comment):
    """Firma una acción pendiente (approval chain)."""
    _enforce_local_only("pending approve")
    from albra.config.settings import Settings
    from albra.matters.store import MatterStore
    from albra.security.approval_chain import (
        ApprovalChain,
        ApprovalChainError,
        UnauthorizedRoleError,
    )
    s = Settings()
    store = MatterStore(s.matter_db_path)
    chain = ApprovalChain(store)
    try:
        updated = chain.approve(action_id, by=by, role=role, comment=comment)
        click.echo(f"Approved. Status: {updated['status']}")
        click.echo(f"  approvals: {len(updated['approvals'])}/{updated['minimum_human_signoff']}")
    except UnauthorizedRoleError as e:
        click.echo(f"Unauthorized: {e}", err=True)
        sys.exit(2)
    except ApprovalChainError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    store.close()


@main.command()
@click.argument("text")
@click.option("--matter", default=None, help="matter_id para contexto")
def research(text, matter):
    """RESEARCH-AGENT con citation audit pre-reveal fail-closed.

    Audita el texto proporcionado y reporta si las citas que contiene
    pasan el pipeline extract -> validate -> retrace -> reveal_or_block.
    """
    from albra.knowledge.citation_audit import CitationAuditor
    auditor = CitationAuditor()
    result = auditor.audit_response(text)
    click.echo("\nResearch audit:")
    if matter:
        click.echo(f"  Matter context: {matter}")
    click.echo(f"  total_citations: {result.total_citations}")
    click.echo(f"  verified: {len(result.verified)}")
    click.echo(f"  unverified: {len(result.unverified)}")
    click.echo(f"  rejected: {len(result.rejected)}")
    click.echo(f"  revealed: {result.revealed}")
    click.echo(f"\nReason: {result.reason}")
    if not result.revealed:
        click.echo("\n[BLOCKED — fail-closed anti-hallucination]")
        if result.unverified:
            click.echo("\nUnverified citations:")
            for c in result.unverified:
                click.echo(f"  - {c.document_name} (article={c.article_number})")
        if result.rejected:
            click.echo("\nRejected (honestly) citations:")
            for c in result.rejected:
                click.echo(f"  - {c.document_name}")
    else:
        if result.verified:
            click.echo("\nVerified citations:")
            for c in result.verified:
                click.echo(f"  - {c.document_name} (article={c.article_number})")


if __name__ == "__main__":
    main()
