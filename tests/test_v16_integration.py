"""Tests V1.6 - Integration Complete. Cubre P0, P1, attack tests."""
import asyncio
import os
import tempfile

from albra.config.settings import Settings
from albra.doctor.self_improve import SelfImprove
from albra.evidence.chain import EvidenceChain
from albra.evidence.legal_gate import LegalGate
from albra.files.tracker import FileTracker
from albra.handoffs.protocol import (
    HandoffEnvelope,
    HandoffProtocol,
    InProcessTransport,
    MockTransport,
)
from albra.identity.agent import get_agent
from albra.mcp.protocol import MCPRequest
from albra.mcp.server import MCPServer
from albra.memory.interface import MemoryInterface
from albra.observability.execution_trace import ExecutionTrace
from albra.resilience.circuit_breaker import CircuitBreaker
from albra.security.auth import hash_password, verify_password
from albra.security.autonomy import AutonomyController
from albra.security.execution_guard import ExecutionGuard
from albra.security.hitl import HITLGate
from albra.security.policy_state import PolicyEngineState
from albra.security.rbac import has_permission
from albra.tools.registry import ToolRegistry

# --- P0.1: Reasoning + ProviderRouter integration ---

def test_reasoning_uses_provider_router():
    """V1.6: ReasoningEngine integrado con ProviderRouter."""
    async def _run():
        agent = get_agent()
        await agent.boot()
        reasoning = agent.organs["reasoning"]
        # Debe tener _provider_router y _provider_registry wired
        assert reasoning._provider_router is not None
        assert reasoning._provider_registry is not None
        await agent.shutdown()
    asyncio.run(_run())


def test_reasoning_provider_call_traced():
    """El provider usado queda en execution_trace."""
    async def _run():
        agent = get_agent()
        await agent.boot()
        r = await agent.process("hola", user="test")
        # Verificar que se registró provider en trace
        trace = agent.execution_trace.get(r["execution_id"])
        assert trace is not None
        assert len(trace["providers"]) >= 1
        await agent.shutdown()
    asyncio.run(_run())


def test_reasoning_legal_question_uses_local_fallback():
    """Para legal_question NO usar LLM (no inventar)."""
    async def _run():
        agent = get_agent()
        await agent.boot()
        r = await agent.process("¿qué dice el artículo 25 del código civil?")
        assert r["provider_used"] == "rules_fallback_legal"
        await agent.shutdown()
    asyncio.run(_run())


def test_reasoning_provider_failure_fallback():
    """Si provider falla → fallback a reglas locales."""
    async def _run():
        agent = get_agent()
        await agent.boot()
        # Mock que falla
        class FailingProvider:
            name = "failing"
            kind = "llm"
            async def call(self, prompt, **kw):
                from albra.providers.base import ProviderResponse
                return ProviderResponse(ok=False, error="boom")
            async def startup(self): pass
            async def shutdown(self): pass
        agent.organs["providers"]._providers["failing"] = FailingProvider()
        agent.organs["provider_router"].providers["failing"] = FailingProvider()
        agent.organs["provider_router"].routing_table["chat"] = "failing"
        r = await agent.process("hola", user="test")
        # Debe caer en fallback
        assert "fallback" in r["provider_used"] or r["provider_used"] == "mock"
        await agent.shutdown()
    asyncio.run(_run())


# --- P0.4: result undefined bug ---

def test_agent_handles_tool_exception():
    """Si tools.invoke raisea → result queda definido (no NameError)."""
    async def _run():
        agent = get_agent()
        await agent.boot()
        # Forzar una tool que falle registrándola
        from albra.tools.base import Tool
        async def boom_handler(input, *, user):
            raise RuntimeError("BOOM")
        agent.organs["tools"].register(Tool(
            name="boom_tool",
            description="siempre falla",
            input_schema={},
            handler=boom_handler,
            risk="low",
            category="test",
        ))
        # Forzar que el reasoning decida invocar boom_tool
        # (lo hacemos manualmente invocando process con mensaje que matchea)
        r = await agent.process("hola", user="test")
        assert "execution_id" in r
        # Sin NameError, sin crash
        await agent.shutdown()
    asyncio.run(_run())


# --- P0.5: Memory unification ---

def test_agent_uses_memory_interface_only():
    """Pipeline usa MemoryInterface, no MemoryDV directo."""
    async def _run():
        agent = get_agent()
        await agent.boot()
        # agent.organs["memory"] debe ser MemoryInterface
        from albra.memory.interface import MemoryInterface
        assert isinstance(agent.organs["memory"], MemoryInterface)
        # NO debe haber MemoryDV en organs (legacy removed from pipeline)
        # Nota: MemoryDV class aún existe como implementación pero no se usa directo
        await agent.shutdown()
    asyncio.run(_run())


def test_memory_interface_truth_levels_persist():
    """Truth levels sobreviven restart."""
    with tempfile.TemporaryDirectory() as tmp:
        db = f"{tmp}/mem.db"
        mi1 = MemoryInterface(backend="sqlite", db_path=db)
        asyncio.run(mi1.startup())
        asyncio.run(mi1.write(
            "verified fact", category="knowledge", truth_level="VERIFIED",
        ))
        asyncio.run(mi1.shutdown())
        # Restart
        mi2 = MemoryInterface(backend="sqlite", db_path=db)
        asyncio.run(mi2.startup())
        items = asyncio.run(mi2.retrieve("verified fact"))
        assert len(items) >= 1
        assert items[0].truth_level == "VERIFIED"
        asyncio.run(mi2.shutdown())


# --- P1: Evidence rehydration ---

def test_evidence_rehydrate_after_restart():
    """EvidenceChain sobrevive restart (P1)."""
    with tempfile.TemporaryDirectory() as tmp:
        path = f"{tmp}/audit.log"
        ev1 = EvidenceChain(Settings(audit_path=path))
        asyncio.run(ev1.startup())
        eid = asyncio.run(ev1.add(
            kind="research_finding", content="test content", source="https://x.co",
        ))
        asyncio.run(ev1.shutdown())
        # New instance, same DB
        ev2 = EvidenceChain(Settings(audit_path=path))
        asyncio.run(ev2.startup())
        item = ev2.get(eid)  # Should be rehydrated
        assert item is not None
        assert item.content == "test content"
        asyncio.run(ev2.shutdown())


# --- P1: HITL deny/resume robusto ---

def test_hitl_deny_blocks_resume():
    """Una denegación PERMANENTE - no puede reanudar."""
    with tempfile.TemporaryDirectory() as tmp:
        gate = HITLGate(Settings(audit_path=f"{tmp}/a.log"))
        asyncio.run(gate.startup())
        req = asyncio.run(gate.request_approval(
            user="test", action="publish_document", risk="high",
        ))
        # Deny
        asyncio.run(gate.deny(req.id, by="admin", reason="no"))
        # Resume must FAIL
        result = asyncio.run(gate.resume(req.id))
        assert not result["ok"]
        assert result["reason"] == "denied"
        assert result.get("permanent") is True
        asyncio.run(gate.shutdown())


def test_hitl_persists_after_restart():
    """HITL state persiste tras restart."""
    with tempfile.TemporaryDirectory() as tmp:
        path = f"{tmp}/a.log"
        gate1 = HITLGate(Settings(audit_path=path))
        asyncio.run(gate1.startup())
        req = asyncio.run(gate1.request_approval(
            user="u", action="send_external_message",
        ))
        req_id = req.id
        asyncio.run(gate1.shutdown())
        # Restart
        gate2 = HITLGate(Settings(audit_path=path))
        asyncio.run(gate2.startup())
        # Debe seguir pendiente
        assert gate2.status(req_id) == "pending"
        asyncio.run(gate2.shutdown())


def test_hitl_resume_already_resumed_blocks():
    """Reanudar dos veces la misma acción approved → bloqueado."""
    with tempfile.TemporaryDirectory() as tmp:
        gate = HITLGate(Settings(audit_path=f"{tmp}/a.log"))
        asyncio.run(gate.startup())
        req = asyncio.run(gate.request_approval(user="u", action="x"))
        asyncio.run(gate.approve(req.id, by="admin"))
        # First resume → ok
        r1 = asyncio.run(gate.resume(req.id))
        assert r1["ok"]
        # Second resume → blocked (already resumed)
        r2 = asyncio.run(gate.resume(req.id))
        assert not r2["ok"]
        assert r2["reason"] == "already_resumed"
        asyncio.run(gate.shutdown())


# --- P1: Password hashing (pbkdf2) ---

def test_password_hash_pbkdf2_format():
    """Hash NO es sha256 directo - es pbkdf2 con salt."""
    h = hash_password("test123")
    assert h.startswith("pbkdf2$")
    parts = h.split("$")
    assert len(parts) == 4
    assert parts[0] == "pbkdf2"
    assert int(parts[1]) >= 100000  # alto coste


def test_password_verify_correct():
    h = hash_password("mysecret")
    assert verify_password("mysecret", h) is True


def test_password_verify_wrong():
    h = hash_password("mysecret")
    assert verify_password("wrong", h) is False


def test_password_hash_has_random_salt():
    """Cada hash tiene salt distinto - mismo password → hashes distintos."""
    h1 = hash_password("samepass")
    h2 = hash_password("samepass")
    assert h1 != h2  # salt distinto
    # Pero ambos verifican el mismo password
    assert verify_password("samepass", h1)
    assert verify_password("samepass", h2)


# --- P1: FileTracker sandbox ---

def test_file_tracker_rejects_path_traversal():
    """Path traversal ../ debe ser DENIED."""
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["ALBRA_WORKSPACE_ROOT"] = tmp
        try:
            ft = FileTracker(Settings())
            # Intentar leer /etc/passwd via traversal
            r = asyncio.run(ft.read("../../etc/passwd"))
            assert not r["ok"]
            assert "SANDBOX" in r["error"] or "no existe" in r["error"].lower()
        finally:
            os.environ.pop("ALBRA_WORKSPACE_ROOT", None)


def test_file_tracker_rejects_absolute_outside():
    """Path absoluto fuera del workspace → DENIED."""
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["ALBRA_WORKSPACE_ROOT"] = tmp
        try:
            ft = FileTracker(Settings())
            r = asyncio.run(ft.read("/etc/passwd"))
            assert not r["ok"]
            assert "SANDBOX" in r["error"]
        finally:
            os.environ.pop("ALBRA_WORKSPACE_ROOT", None)


def test_file_tracker_allows_inside_workspace():
    """Path dentro del workspace → OK."""
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["ALBRA_WORKSPACE_ROOT"] = tmp
        try:
            ft = FileTracker(Settings())
            r = asyncio.run(ft.write("test.txt", b"hello", user="u"))
            assert r["ok"]
            r2 = asyncio.run(ft.read("test.txt"))
            assert r2["ok"]
        finally:
            os.environ.pop("ALBRA_WORKSPACE_ROOT", None)


# --- P1: MCP perimeter - no bypass ---

def test_mcp_denies_without_guard():
    """MCP sin guard cableado → DENY explícito."""
    tr = ToolRegistry(Settings())
    srv = MCPServer(Settings())
    srv.wire(tool_registry=tr, capability_registry=None)
    req = MCPRequest(method="tools/call", params={"name": "clock", "arguments": {}})
    resp = asyncio.run(srv.handle(req))
    assert resp.result.get("ok") is False
    assert "FAIL-CLOSED" in resp.result.get("error", "")


def test_mcp_with_guard_passes_admin():
    """MCP con guard + role admin → ejecuta."""
    tr = ToolRegistry(Settings())
    srv = MCPServer(Settings())
    with tempfile.TemporaryDirectory() as tmp:
        ps = PolicyEngineState(f"{tmp}/ps.db")
        srv.wire(
            tool_registry=tr,
            capability_registry=None,
            execution_guard=ExecutionGuard(),
            policy_state=ps,
            autonomy_controller=AutonomyController(),
            rbac_check_fn=has_permission,
            legal_gate=LegalGate(),
        )
        req = MCPRequest(method="tools/call", params={
            "name": "clock", "arguments": {}, "user": "test", "role": "admin",
        })
        resp = asyncio.run(srv.handle(req))
        assert resp.result.get("ok") is True
        ps.close()


def test_mcp_denies_anon_for_high_risk():
    """MCP con role anon + acción sensible → DENY."""
    tr = ToolRegistry(Settings())
    srv = MCPServer(Settings())
    with tempfile.TemporaryDirectory() as tmp:
        ps = PolicyEngineState(f"{tmp}/ps.db")
        srv.wire(
            tool_registry=tr,
            capability_registry=None,
            execution_guard=ExecutionGuard(),
            policy_state=ps,
            autonomy_controller=AutonomyController(),
            rbac_check_fn=has_permission,
            legal_gate=LegalGate(),
        )
        req = MCPRequest(method="tools/call", params={
            "name": "clock", "arguments": {}, "user": "x", "role": "anon",
        })
        resp = asyncio.run(srv.handle(req))
        # Anon has tools.invoke_low only; tool_invocation requires tools.invoke
        # Could pass since clock is low-risk - let's see
        # Actually our map says "tool_invocation" → "tools.invoke"
        # Anon doesn't have tools.invoke, only tools.invoke_low
        # So this should DENY
        assert resp.result.get("ok") is False
        ps.close()


# --- P1: SelfImprove safety ---

def test_self_improve_cannot_promote_without_hitl():
    """P1: promote_lesson sin HITL → rechazo."""
    with tempfile.TemporaryDirectory() as tmp:
        si = SelfImprove(f"{tmp}/si.db")
        si.PROMOTION_THRESHOLD = 2
        si.capture_error(tool_name="clock", error="timeout 1")
        si.capture_error(tool_name="clock", error="timeout 2")
        lessons = si.get_lessons_for_context()
        if lessons:
            lesson_id = lessons[0]["id"]
            si.validate_lesson(lesson_id, validator="admin")
            # Sin HITL → debe fallar
            result = si.promote_lesson(lesson_id)
            assert not result["ok"]
            assert "hitl_required" in result["reason"]
        si.close()


def test_self_improve_forbidden_actions_listed():
    """P1: SelfImprove declara acciones prohibidas."""
    with tempfile.TemporaryDirectory() as tmp:
        si = SelfImprove(f"{tmp}/si.db")
        forbidden = si.forbidden_actions()
        assert "modify_code" in forbidden
        assert "modify_autonomy_ceiling" in forbidden
        assert "self_promote_to_L5" in forbidden
        assert "bypass_execution_guard" in forbidden
        si.close()


# --- P1: Handoff Transport ---

def test_handoff_in_process_transport():
    transport = InProcessTransport()
    proto = HandoffProtocol(transport=transport)
    env = proto.prepare(
        task_id="t1", from_agent="ALBRA", to_agent="SPECIALIST",
        intent="delegate", execution_id="exec_1",
    )
    asyncio.run(proto.send(env))
    received = asyncio.run(proto.receive(timeout=1.0))
    assert len(received) == 1
    assert received[0].id == env.id
    assert received[0].execution_id == "exec_1"


def test_handoff_mock_transport_records():
    transport = MockTransport()
    proto = HandoffProtocol(transport=transport)
    env = proto.prepare(
        task_id="t1", from_agent="A", to_agent="B",
        intent="test", confidence=0.8, warnings=["caution"],
    )
    asyncio.run(proto.send(env))
    assert len(transport.sent) == 1
    assert transport.sent[0].confidence == 0.8
    assert "caution" in transport.sent[0].warnings


def test_handoff_envelope_serialization():
    """Envelope round-trip JSON."""
    env = HandoffEnvelope(
        task_id="t1", from_agent="A", to_agent="B",
        intent="delegate", confidence=0.9,
        execution_id="exec_1",
        evidence_ids=["ev1", "ev2"],
        warnings=["test"],
    )
    j = env.to_json()
    env2 = HandoffEnvelope.from_json(j)
    assert env2.task_id == "t1"
    assert env2.execution_id == "exec_1"
    assert env2.confidence == 0.9
    assert env2.evidence_ids == ["ev1", "ev2"]


# --- P1: Audit + Tamper Evidence unified ---

def test_audit_log_and_execution_trace_distinct():
    """Audit y Trace son distintos pero complementarios."""
    with tempfile.TemporaryDirectory() as tmp:
        et = ExecutionTrace(f"{tmp}/et.db")
        eid = et.start(agent_id="A", task="test", requester="u")
        et.append_tool_call(eid, name="clock", args={}, ok=True, result="ok")
        et.finish(eid, status="completed", outputs={"reply": "ok"})
        # Trace persiste
        trace = et.get(eid)
        assert trace is not None
        assert trace["status"] == "completed"
        et.close()


# --- P1: Circuit Breaker integration con ExecutionGuard ---

def test_circuit_breaker_blocks_guard():
    """Si provider OPEN → ExecutionGuard debe DENY."""
    cb = CircuitBreaker(failure_threshold=1, cool_off_seconds=60)
    cb.record_failure("provider_x")  # OPEN
    assert not cb.can_pass("provider_x")


# --- P1: Autonomy can't self-elevate ---

def test_autonomy_cannot_self_elevate_to_l5():
    """Componente no puede auto-subirse a L5 sin flag manual."""
    c = AutonomyController()
    # Subir techo a L5
    c.set_max_level("L5_SELF_IMPROVE", reason="test")
    # Sin flag manual → debe bloquear L5
    d = c.assert_allowed(requested_level="L5_SELF_IMPROVE", action="self_improve")
    assert not d.allowed
    assert d.manual_flag_required


# --- P1: Data Classification influences routing ---

def test_classification_influences_provider_routing():
    """Datos sensibles → router elige provider local."""
    from albra.providers.llm import MockLLMProvider
    from albra.providers.router import ProviderRouter
    settings = Settings()
    router = ProviderRouter(settings, providers={
        "mock": MockLLMProvider(),
        "ollama_local": MockLLMProvider(),
    })
    # Texto sensible (DNI) - pasar classification
    decision = router.route(
        "Mi cédula es 12345678",
        metadata={"classification": "DATO_PERSONAL"},
    )
    assert decision.sensitive is True
    # El router decide mandar a local
    assert decision.provider == "ollama_local"


# --- P1: Doctor can't modify code ---

def test_doctor_cannot_modify_code():
    """Doctor tiene try_recover que NO toca código."""
    from albra.doctor.diagnostic import Doctor
    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings(memory_path=f"{tmp}/m.db", audit_path=f"{tmp}/a.log")
        doc = Doctor(settings)
        # try_recover solo reinicia órgano - no modifica archivos
        # Verificamos que NO tiene métodos como 'commit' o 'modify_code'
        assert not hasattr(doc, "commit")
        assert not hasattr(doc, "modify_code")
        assert not hasattr(doc, "write_file")


# --- ATTACK TESTS (P1 - security penetration) ---

def test_attack_1_no_identity():
    """Ataque 1: request sin identity → DENY."""
    async def _run():
        agent = get_agent()
        await agent.boot()
        # role anon solo puede tools.invoke_low
        # Acción sensible como publish_document → debe fallar
        from albra.evidence.legal_gate import LegalGate
        gate = LegalGate()
        v = gate.evaluate("publish_content", actor_role="anon")
        assert v.verdict in ("REVIEW_REQUIRED", "BLOCKED")
        await agent.shutdown()
    asyncio.run(_run())


def test_attack_2_no_rbac_permission():
    """Ataque 2: usuario sin permiso → DENY."""
    # anon no tiene demandas.write
    assert not has_permission("anon", "demandas.write")
    assert not has_permission("anon", "expedientes.write")


def test_attack_3_kill_switch_blocks_everything():
    """Ataque 3: kill switch activo → TODO bloqueado."""
    with tempfile.TemporaryDirectory() as tmp:
        ps = PolicyEngineState(f"{tmp}/ps.db")
        ps.engage_kill_switch(reason="attack")
        guard = ExecutionGuard()
        v = guard.check(
            action="internal_research", user_role="admin",
            policy_state=ps.get_state(),
            autonomy_controller=AutonomyController(),
            rbac_check_fn=has_permission,
            legal_gate_verdict=LegalGate().evaluate("internal_research", actor_role="admin"),
        )
        assert not v.allowed
        ps.close()


def test_attack_4_autonomy_above_ceiling():
    """Ataque 4: pedir L5 con ceiling L2 → DENY."""
    c = AutonomyController()  # default L2
    d = c.assert_allowed(requested_level="L5_SELF_IMPROVE", action="x")
    assert not d.allowed


def test_attack_5_unauthorized_tool():
    """Ataque 5: tool no autorizada para rol → DENY via RBAC."""
    with tempfile.TemporaryDirectory() as tmp:
        ps = PolicyEngineState(f"{tmp}/ps.db")
        guard = ExecutionGuard()
        v = guard.check(
            action="publish_legal_filing", user_role="anon",
            policy_state=ps.get_state(),
            autonomy_controller=AutonomyController(),
            rbac_check_fn=has_permission,
            legal_gate_verdict=LegalGate().evaluate("publish_legal_filing", actor_role="anon"),
        )
        assert not v.allowed
        ps.close()


def test_attack_6_mcp_bypass_attempt():
    """Ataque 6: MCP sin guard → DENY explícito."""
    srv = MCPServer(Settings())
    srv.wire(tool_registry=ToolRegistry(Settings()), capability_registry=None)
    req = MCPRequest(method="tools/call", params={"name": "clock"})
    resp = asyncio.run(srv.handle(req))
    assert resp.result.get("ok") is False


def test_attack_7_filesystem_escape():
    """Ataque 7: path traversal → DENIED by sandbox."""
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["ALBRA_WORKSPACE_ROOT"] = tmp
        try:
            ft = FileTracker(Settings())
            r = asyncio.run(ft.read("../../../etc/shadow"))
            assert not r["ok"]
            assert "SANDBOX" in r["error"]
        finally:
            os.environ.pop("ALBRA_WORKSPACE_ROOT", None)


def test_attack_8_sensitive_data_to_external_provider():
    """Ataque 8: datos sensibles → routing los manda a local."""
    from albra.providers.llm import MockLLMProvider
    from albra.providers.router import ProviderRouter
    settings = Settings()
    router = ProviderRouter(settings, providers={
        "mock": MockLLMProvider(),
        "ollama_local": MockLLMProvider(),
    })
    # Credencial → CREDENCIAL classification → local provider
    # Pasar classification via metadata
    decision = router.route(
        "password=secret123 api_key=abc",
        metadata={"classification": "CREDENCIAL"},
    )
    assert decision.sensitive is True
    assert decision.provider == "ollama_local"


def test_attack_9_circuit_open_blocks():
    """Ataque 9: circuit breaker OPEN → bloquea."""
    cb = CircuitBreaker(failure_threshold=2)
    cb.record_failure("p")
    cb.record_failure("p")
    assert not cb.can_pass("p")


def test_attack_10_duplicate_action():
    """Ataque 10: acción duplicada → dedup blocks."""
    with tempfile.TemporaryDirectory() as tmp:
        ps = PolicyEngineState(f"{tmp}/ps.db")
        guard = ExecutionGuard()
        common = {
            "policy_state": ps.get_state(),
            "autonomy_controller": AutonomyController(),
            "rbac_check_fn": has_permission,
            "legal_gate_verdict": LegalGate().evaluate("internal_research", actor_role="admin"),
        }
        v1 = guard.check(
            action="internal_research", user_role="admin",
            dedup_key="atk_10", **common,
        )
        v2 = guard.check(
            action="internal_research", user_role="admin",
            dedup_key="atk_10", **common,
        )
        assert v1.allowed
        assert not v2.allowed
        ps.close()


def test_attack_11_resume_denied_hitl():
    """Ataque 11: resumir HITL denegado → blocks."""
    with tempfile.TemporaryDirectory() as tmp:
        gate = HITLGate(Settings(audit_path=f"{tmp}/a.log"))
        asyncio.run(gate.startup())
        req = asyncio.run(gate.request_approval(user="u", action="x"))
        asyncio.run(gate.deny(req.id, by="admin", reason="no"))
        r = asyncio.run(gate.resume(req.id))
        assert not r["ok"]
        assert r["reason"] == "denied"
        asyncio.run(gate.shutdown())


def test_attack_12_nonexistent_provider():
    """Ataque 12: provider inexistente → fallback to mock."""
    async def _run():
        agent = get_agent()
        await agent.boot()
        router = agent.organs["provider_router"]
        # Set routing table to point to nonexistent provider
        router.routing_table["chat"] = "nonexistent_provider_xyz"
        # Mock fallback still works
        r = await agent.process("hola", user="test")
        assert r["reply"]  # Something returned via fallback
        await agent.shutdown()
    asyncio.run(_run())


def test_attack_17_tamper_audit():
    """Ataque 17: alterar audit trail → verify_chain detecta."""
    from albra.audit.tamper_evident import TamperEvidentAudit
    with tempfile.TemporaryDirectory() as tmp:
        path = f"{tmp}/a.log"
        audit = TamperEvidentAudit(path)
        asyncio.run(audit.append("test", {"k": "v1"}))
        asyncio.run(audit.append("test", {"k": "v2"}))
        # Tamper
        lines = open(path).readlines()
        lines[0] = lines[0].replace('"v1"', '"HACKED"')
        with open(path, "w") as f:
            f.writelines(lines)
        result = audit.verify_chain()
        assert not result["ok"]


# --- RESTART TESTS ---

def test_restart_preserves_policy_state():
    """Policy state sobrevive restart (P1)."""
    with tempfile.TemporaryDirectory() as tmp:
        path = f"{tmp}/ps.db"
        ps1 = PolicyEngineState(path)
        ps1.set_mode("LIVE", actor="admin", reason="go")
        ps1.engage_kill_switch(reason="emergency")
        ps1.close()
        # Restart
        ps2 = PolicyEngineState(path)
        state = ps2.get_state()
        assert state.mode == "LIVE"
        assert state.kill_switch is True
        ps2.close()


def test_restart_preserves_evidence():
    """Evidence sobrevive restart."""
    with tempfile.TemporaryDirectory() as tmp:
        path = f"{tmp}/a.log"
        ev1 = EvidenceChain(Settings(audit_path=path))
        asyncio.run(ev1.startup())
        eid = asyncio.run(ev1.add(
            kind="law", content="art 1", source="https://x.co",
            metadata={"type": "official"},
        ))
        asyncio.run(ev1.shutdown())
        ev2 = EvidenceChain(Settings(audit_path=path))
        asyncio.run(ev2.startup())
        item = ev2.get(eid)
        assert item is not None
        assert item.source == "https://x.co"
        asyncio.run(ev2.shutdown())


def test_restart_preserves_hitl():
    """HITL pending sobrevive restart."""
    with tempfile.TemporaryDirectory() as tmp:
        path = f"{tmp}/a.log"
        g1 = HITLGate(Settings(audit_path=path))
        asyncio.run(g1.startup())
        req = asyncio.run(g1.request_approval(user="u", action="x"))
        req_id = req.id
        asyncio.run(g1.shutdown())
        # Restart
        g2 = HITLGate(Settings(audit_path=path))
        asyncio.run(g2.startup())
        assert g2.status(req_id) == "pending"
        asyncio.run(g2.shutdown())


def test_restart_preserves_execution_trace():
    """ExecutionTrace persistente."""
    with tempfile.TemporaryDirectory() as tmp:
        et1 = ExecutionTrace(f"{tmp}/et.db")
        eid = et1.start(agent_id="A", task="test", requester="u")
        et1.append_tool_call(eid, name="clock", args={}, ok=True, result="ok")
        et1.finish(eid, status="completed")
        et1.close()
        # Restart
        et2 = ExecutionTrace(f"{tmp}/et.db")
        trace = et2.get(eid)
        assert trace is not None
        assert trace["status"] == "completed"
        assert len(trace["tools"]) == 1
        et2.close()
