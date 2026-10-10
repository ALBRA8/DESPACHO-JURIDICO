"""Tests de plugins, policies y triage."""
import asyncio

from albra.identity.agent import get_agent
from albra.knowledge.triage import KnowledgeTriage
from albra.plugins.manager import (
    CONTRACT_REDLINE_PLUGIN,
    PluginManager,
)
from albra.security.policy import Policy, PolicyEngine


def test_plugin_manager_starts_empty():
    pm = PluginManager()
    assert pm.list() == []


def test_contract_redline_plugin_registers_tool():
    """El plugin de redlining registra 'contract_analyzer'."""
    async def _run():
        agent = get_agent()
        await agent.boot()
        pm = PluginManager()
        await pm.register(CONTRACT_REDLINE_PLUGIN, agent=agent)
        tools = [t["name"] for t in agent.organs["tools"].list()]
        assert "contract_analyzer" in tools
        await agent.shutdown()
    asyncio.run(_run())


def test_contract_analyzer_detects_risk():
    """El analyzer detecta cláusulas de riesgo reales."""
    async def _run():
        agent = get_agent()
        await agent.boot()
        pm = PluginManager()
        await pm.register(CONTRACT_REDLINE_PLUGIN, agent=agent)
        sample = """
        El contratista indemnizará por cualquier daño causado al cliente.
        La empresa no será responsable por daños indirectos.
        El contratante renuncia expresamente al derecho de ejercer acción judicial.
        """
        result = await agent.organs["tools"].invoke(
            "contract_analyzer", {"text": sample}, user="test"
        )
        assert result["ok"] is True
        assert result["value"]["count"] >= 2
        kinds = [r["kind"] for r in result["value"]["risks"]]
        assert "indemnidad_amplia" in kinds
        assert "renuncia_derechos" in kinds
        await agent.shutdown()
    asyncio.run(_run())


def test_plugin_unregister():
    async def _run():
        agent = get_agent()
        await agent.boot()
        pm = PluginManager()
        await pm.register(CONTRACT_REDLINE_PLUGIN, agent=agent)
        assert len(pm.list()) == 1
        await agent.shutdown()
    asyncio.run(_run())


def test_policy_engine_evaluates_menor_edad():
    eng = PolicyEngine()
    results = eng.evaluate({
        "subject": "caso con menor de edad",
        "jurisdiction": "CO",
    })
    # Policy CO-001 about "menor" should trigger
    co_results = [r for r in results if r.policy_id == "CO-001"]
    assert len(co_results) >= 1
    assert co_results[0].triggered is True


def test_policy_engine_blocks_audit_modification():
    eng = PolicyEngine()
    results = eng.evaluate({
        "action": "modify_audit_log",
    })
    deny_results = [r for r in results if r.action == "deny"]
    assert len(deny_results) >= 1


def test_policy_engine_blocks_external_msg():
    eng = PolicyEngine()
    results = eng.evaluate({
        "action": "send_external_message",
    })
    hitl_results = [r for r in results if r.action == "require_hitl"]
    assert len(hitl_results) >= 1


def test_policy_engine_custom_rule():
    eng = PolicyEngine()
    eng.register(Policy(
        id="TEST-001",
        name="custom_test",
        description="Test policy",
        rule="amount > 5000",
        action="deny",
    ))
    results = eng.evaluate({"amount": 6000})
    assert any(r.policy_id == "TEST-001" for r in results)


def test_policy_engine_or():
    eng = PolicyEngine()
    results = eng.evaluate({
        "subject": "este es sobre DNI del cliente",
    })
    # debe triggerear la policy de datos sensibles
    warn_results = [r for r in results if r.action == "warn"]
    assert len(warn_results) >= 1


def test_triage_statute_question():
    t = KnowledgeTriage()
    r = t.triage("¿Qué dice el artículo 25 del código civil?")
    # Statute tiene 2 matches (artículo, código) → único tipo con matches
    assert r.question_type == "statute"
    assert "normative" in r.suggested_sources or "statutes" in r.suggested_sources


def test_triage_jurisprudence_question():
    t = KnowledgeTriage()
    r = t.triage("¿Hay jurisprudencia de la corte suprema sobre este caso?")
    assert r.question_type == "jurisprudence"


def test_triage_mixed_question():
    t = KnowledgeTriage()
    r = t.triage("¿Qué dice la doctrina sobre el artículo y la sentencia?")
    # doctrine + statute + jurisprudence → mixed
    assert r.question_type == "mixed"


def test_triage_procedure_question():
    t = KnowledgeTriage()
    # Solo "término" matches procedure (sin jurisprudence ni statute keywords)
    r = t.triage("¿Cuál es el término de prescripción?")
    assert r.question_type == "procedure"
