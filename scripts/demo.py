"""Script de demo - prueba el agente ALBRA end-to-end."""
import asyncio
import sys
import os

# Asegurar que albra esté en el path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from albra.identity.agent import get_agent
from albra.identity.manifest import AGENT_MANIFEST


async def main():
    print("=" * 70)
    print(f"🧬 {AGENT_MANIFEST.name} v{AGENT_MANIFEST.version}")
    print(f"   Codename: {AGENT_MANIFEST.codename}")
    print(f"   Jurisdicción: {AGENT_MANIFEST.jurisdiction}")
    print(f"   Órganos: {len(AGENT_MANIFEST.organs)}")
    print("=" * 70)

    agent = get_agent()
    print("\n🚀 Booting organism...")
    await agent.boot()
    print(f"✅ {len(agent.organs)} órganos inicializados")

    # Demo 1: saludo
    print("\n--- DEMO 1: Saludo ---")
    r = await agent.process("Hola bro, qué más!", channel="text", user="test_user")
    print(f"User: Hola bro, qué más!")
    print(f"ALBRA: {r['reply']}")
    print(f"(authorized={r['authorized']}, tools_used={r['tools_used']}, memory_used={r['memory_used']})")

    # Demo 2: pregunta legal (debe rehusar)
    print("\n--- DEMO 2: Pregunta legal sin conocimiento cargado ---")
    r = await agent.process("¿Qué dice el artículo 25 del código civil colombiano?", user="test_user")
    print(f"User: ¿Qué dice el artículo 25 del código civil colombiano?")
    print(f"ALBRA: {r['reply']}")

    # Demo 3: uso de tool
    print("\n--- DEMO 3: Uso de herramienta ---")
    r = await agent.process("calcula 7 * 8", user="test_user")
    print(f"User: calcula 7 * 8")
    print(f"ALBRA: {r['reply']}")
    print(f"(tools_used: {r['tools_used']})")

    # Demo 4: estado del agente
    print("\n--- DEMO 4: Health check ---")
    r = await agent.process("¿cuál es el estado del agente?", user="test_user")
    print(f"User: ¿cuál es el estado del agente?")
    print(f"ALBRA: {r['reply']}")

    # Demo 5: Doctor
    print("\n--- DEMO 5: Diagnóstico del Doctor ---")
    doc = agent.organs["doctor"]
    report = await doc.diagnose(scope="all")
    summary = report.build_summary()
    print(f"Summary: {summary}")
    for c in report.checks[:5]:
        status = "✅" if c.severity == "ok" else "⚠️" if c.severity == "warn" else "❌"
        print(f"  {status} [{c.organ}] {c.detail}")

    # Demo 6: Memory stats
    print("\n--- DEMO 6: Memory stats ---")
    mem = agent.organs["memory"]
    print(f"Stats: {mem.stats()}")

    # Demo 7: Plugin contract redlining
    print("\n--- DEMO 7: Plugin Contract Redlining ---")
    from albra.plugins.manager import PluginManager, CONTRACT_REDLINE_PLUGIN
    pm = PluginManager()
    await pm.register(CONTRACT_REDLINE_PLUGIN, agent=agent)
    print("Plugins cargados:")
    for p in pm.list():
        print(f"  - {p['name']} v{p['version']}")

    sample_contract = """
    CONTRATO DE PRESTACIÓN DE SERVICIOS
    CLÁUSULA PRIMERA: El contratista indemnizará por cualquier daño causado.
    CLÁUSULA SEGUNDA: La empresa no será responsable por daños indirectos.
    CLÁUSULA TERCERA: El contratante renuncia expresamente al derecho de ejercer acción judicial.
    CLÁUSULA CUARTA: Confidencialidad perpetua - nunca podrá divulgar.
    """
    result = await agent.organs["tools"].invoke(
        "contract_analyzer", {"text": sample_contract}, user="test_user"
    )
    if result["ok"]:
        print(f"\n🚨 Cláusulas de riesgo detectadas: {result['value']['count']}")
        for risk in result["value"]["risks"]:
            print(f"  - [{risk['severity']:6s}] {risk['kind']:30s} - {risk['snippet'][:60]}...")

    # Demo 8: Workflow graph
    print("\n--- DEMO 8: Workflow Graph (demanda civil) ---")
    from albra.workflows.graph import build_demand_workflow
    g = build_demand_workflow()
    run = await g.run({"cliente": "Juan", "caso": "demanda civil"})
    print(f"Estado: {run.status}")
    print(f"Visitados: {run.visited}")
    if run.interrupted_at:
        print(f"⏸️  Interrumpido en: {run.interrupted_at} (esperando HITL)")
        # Simular aprobación
        run = await g.resume(run.id, approved=True)
        print(f"Tras aprobación: estado={run.status}")
        print(f"Visitados finales: {run.visited}")

    # Demo 9: Tamper-evident audit
    print("\n--- DEMO 9: Tamper-Evident Audit ---")
    from albra.audit.tamper_evident import TamperEvidentAudit
    from albra.config.settings import Settings
    s = Settings()
    audit = TamperEvidentAudit(s.audit_path)
    verify = audit.verify_chain()
    print(f"Chain OK: {verify['ok']}, total entries: {verify['total']}")
    print(f"Fingerprint: {audit.fingerprint()[:32]}...")

    # Shutdown
    print("\n--- Shutdown ---")
    await agent.shutdown()
    print("✅ Agente apagado correctamente")


if __name__ == "__main__":
    asyncio.run(main())
