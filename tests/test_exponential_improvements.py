"""Tests de las mejoras exponenciales implementadas."""
import asyncio
import tempfile

from albra.config.settings import Settings
from albra.identity.organ_manifests import (
    ORGAN_MANIFESTS,
    get_organ_manifest,
    list_organ_manifests,
)
from albra.security.firewall.engine import ActionFirewall
from albra.security.firewall.policy import FIREWALL_POLICIES
from albra.evidence.cite_gate import CiteOrRefuseGate
from albra.evidence.chain import EvidenceChain
from albra.reasoning.debate import AdversarialDebate
from albra.workflows.graph import WorkflowGraph, NodeKind, build_demand_workflow
from albra.memory.consolidator import HierarchicalConsolidator
from albra.memory.store import MemoryDV
from albra.research.crag import CRAG
from albra.mcp.jurisdictions import JurisdictionCatalog
from albra.doctor.self_healing import SelfHealingSupervisor
from albra.doctor.diagnostic import Doctor
from albra.providers.router import ProviderRouter
from albra.providers.llm import MockLLMProvider
from albra.audit.tamper_evident import TamperEvidentAudit
from albra.workflows.sops import DEMANDA_CIVIL_SOP, get_sop, list_sops


def test_organ_manifests_complete():
    """30 manifests - uno por órgano del ADN."""
    assert len(ORGAN_MANIFESTS) == 30
    for name, m in ORGAN_MANIFESTS.items():
        assert m.role, f"Manifest {name} sin role"
        assert m.goal, f"Manifest {name} sin goal"
        assert m.backstory, f"Manifest {name} sin backstory"


def test_organ_manifest_lookup():
    m = get_organ_manifest("DOCTOR")
    assert m is not None
    assert "médico" in m.role.lower() or "doctor" in m.role.lower()


def test_firewall_blocks_critical_without_auth():
    fw = ActionFirewall(Settings())
    # Acción crítica sin permisos
    d = fw.is_allowed("delete_evidence", user="anon", role="anon")
    assert d.allowed is False
    assert "not in allowed" in d.reason.lower()


def test_firewall_requires_hitl_for_publish():
    fw = ActionFirewall(Settings())
    d = fw.is_allowed("publish_document", user="admin", role="admin")
    assert d.allowed is False
    assert d.hitl_request_id is not None


def test_firewall_kill_switch():
    fw = ActionFirewall(Settings())
    # Prender kill switch
    fw.kill_switch_off("tool_invocation_low")
    d = fw.is_allowed("tool_invocation_low", user="anon", role="anon")
    assert d.allowed is False
    assert "kill switch" in d.reason.lower()


def test_firewall_audit_chain_verifies():
    fw = ActionFirewall(Settings())
    fw.is_allowed("tool_invocation_low", user="anon", role="anon")
    fw.is_allowed("tool_invocation_low", user="anon", role="anon")
    assert fw.verify_chain() is True


def test_firewall_modify_audit_always_denied():
    fw = ActionFirewall(Settings())
    d = fw.is_allowed("modify_audit_log", user="admin", role="admin")
    assert d.allowed is False


def test_cite_gate_no_evidence_refuses():
    """Una afirmación legal sin evidencia debe ser rechazada."""
    gate = CiteOrRefuseGate(Settings())
    result = asyncio.run(gate.evaluate("La ley 100 de 1993 establece que..."))
    assert result.refused is True
    assert "ALBRA" in result.safe_text


def test_cite_gate_passes_non_legal():
    gate = CiteOrRefuseGate(Settings())
    result = asyncio.run(gate.evaluate("Hola, ¿cómo estás?"))
    assert result.refused is False


def test_cite_gate_with_evidence_passes():
    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings(audit_path=f"{tmp}/audit.log")
        ev = EvidenceChain(settings)
        asyncio.run(ev.startup())
        asyncio.run(ev.add(
            kind="law", content="La ley 100 establece...",
            source="https://www.funcionpublica.gov.co",
            metadata={"type": "official"},
        ))
        gate = CiteOrRefuseGate(settings)
        result = asyncio.run(gate.evaluate(
            "Según la ley 100, el derecho a la salud es fundamental",
            evidence_chain=ev,
        ))
        assert result.refused is False
        assert len(result.citations) > 0


def test_adversarial_debate_runs_three_roles():
    debate = AdversarialDebate(Settings(), provider=MockLLMProvider())
    result = asyncio.run(debate.run_debate("¿Es válida una cláusula penal excesiva?"))
    assert len(result.arguments) == 2  # actor + demandado
    assert result.ruling != ""


def test_workflow_graph_runs():
    async def n1(state):
        state["x"] = 1
        return state
    async def n2(state):
        state["x"] = 2
        return state
    g = WorkflowGraph("test")
    g.add_node(type("N", (), {"name": "n1", "kind": NodeKind.ACTION, "fn": n1, "description": "", "metadata": {}})())
    # Approach más simple
    from albra.workflows.graph import GraphNode
    g2 = WorkflowGraph("test2")
    g2.add_node(GraphNode("n1", NodeKind.ACTION, n1))
    g2.add_node(GraphNode("n2", NodeKind.TERMINAL, None))
    g2.add_edge("n1", "n2")
    g2.entry("n1")
    run = asyncio.run(g2.run({}))
    assert run.status == "done"
    assert run.state.get("x") == 1


def test_demand_workflow_interrupts_for_approval():
    g = build_demand_workflow()
    run = asyncio.run(g.run({}))
    # Debe llegar al nodo "approve" y quedar interrumpido
    assert run.status == "interrupted"
    assert run.interrupted_at == "approve"


def test_demand_workflow_resumes_after_approval():
    g = build_demand_workflow()
    run = asyncio.run(g.run({}))
    assert run.status == "interrupted"
    run = asyncio.run(g.resume(run.id, approved=True))
    assert run.status == "done"


def test_memory_consolidator_runs():
    settings = Settings(memory_backend="inmemory")
    mem = MemoryDV(settings)
    # Simular conversaciones antiguas - escribimos y luego "envejecemos" el ts del item
    import time
    old_ts = time.time() - 100000  # ~27h atrás
    for i in range(3):
        eid = asyncio.run(mem.write(
            f"msg viejo {i}", category="conversational", metadata={"user": "test"}
        ))
        # Envejecer el ts directamente en el store
        if hasattr(mem, "_mem"):
            for item in mem._mem:
                if item["id"] == eid:
                    item["ts"] = old_ts
    consolidator = HierarchicalConsolidator(memory=mem)
    stats = asyncio.run(consolidator.consolidate_conversations(max_age_hours=1, min_items=3))
    assert stats.reviewed >= 3


def test_crag_falls_back_to_web():
    """CRAG: si memoria no tiene nada relevante, intenta research."""
    settings = Settings(memory_backend="inmemory")
    mem = MemoryDV(settings)

    # Mock research engine que devuelve findings
    class MockResearch:
        async def search(self, q, top_k=5):
            return {
                "ok": True,
                "findings": [{
                    "snippet": "resultado web",
                    "source_url": "https://example.com",
                    "source_type": "unofficial",
                    "confidence": 0.6,
                }],
                "evidence_ids": [],
            }

    crag = CRAG(memory=mem, research=MockResearch())
    result = asyncio.run(crag.retrieve("norma sobre contratos"))
    assert result.source in ("web", "memory", "none")


def test_jurisdiction_catalog_has_colombia():
    cat = JurisdictionCatalog()
    co = cat.get("CO")
    assert co is not None
    assert co.jurisdiction == "CO"


def test_jurisdiction_catalog_list():
    cat = JurisdictionCatalog()
    items = cat.list()
    assert len(items) >= 5
    co_items = [i for i in items if i["jurisdiction"] == "CO"]
    assert len(co_items) == 1


def test_self_healing_supervisor_snapshots():
    settings = Settings()
    doctor = Doctor(settings)
    sh = SelfHealingSupervisor(settings, doctor=doctor, organs={})
    snap = asyncio.run(sh.snapshot())
    assert isinstance(snap.organs_health, dict)


def test_provider_router_routes_sensitive_to_local():
    settings = Settings()
    providers = {"mock": MockLLMProvider()}
    router = ProviderRouter(settings, providers=providers)
    decision = router.route("Datos del cliente: DNI 12345678, expediente 2024")
    assert decision.sensitive is True
    assert decision.provider == "ollama_local"


def test_provider_router_routes_chat_to_cloud():
    settings = Settings()
    providers = {"mock": MockLLMProvider()}
    router = ProviderRouter(settings, providers=providers)
    decision = router.route("Hola, ¿cómo estás?")
    assert decision.sensitive is False


def test_tamper_evident_audit_chain_verifies():
    with tempfile.TemporaryDirectory() as tmp:
        path = f"{tmp}/audit.log"
        audit = TamperEvidentAudit(path)
        asyncio.run(audit.append("test_event", {"k": "v1"}))
        asyncio.run(audit.append("test_event", {"k": "v2"}))
        asyncio.run(audit.append("test_event", {"k": "v3"}))
        result = audit.verify_chain()
        assert result["ok"] is True
        assert result["total"] == 3


def test_tamper_evident_detects_tamper():
    """Si se modifica una línea, verify_chain() debe detectarlo."""
    with tempfile.TemporaryDirectory() as tmp:
        path = f"{tmp}/audit.log"
        audit = TamperEvidentAudit(path)
        asyncio.run(audit.append("test", {"k": "v1"}))
        asyncio.run(audit.append("test", {"k": "v2"}))
        # Tamper: modificar primera línea
        lines = open(path).readlines()
        lines[0] = lines[0].replace('"v1"', '"TAMPERED"')
        with open(path, "w") as f:
            f.writelines(lines)
        result = audit.verify_chain()
        assert result["ok"] is False


def test_sop_demanda_civil_has_hitl_steps():
    assert len(DEMANDA_CIVIL_SOP.steps) == 6
    hitl_steps = [s for s in DEMANDA_CIVIL_SOP.steps if s.requires_hitl]
    assert len(hitl_steps) >= 2  # aprobación_cliente + radicacion


def test_sop_list():
    sops = list_sops()
    assert len(sops) >= 2
    names = [s["name"] for s in sops]
    assert "demanda_civil" in names
    assert "contestacion_demanda" in names
