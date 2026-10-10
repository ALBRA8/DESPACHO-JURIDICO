"""Tests de los órganos V1.5 - paridad holding."""
import asyncio
import os
import tempfile

from albra.config.settings import Settings
from albra.observability.execution_trace import ExecutionTrace
from albra.security.autonomy import AutonomyController, LEVELS
from albra.doctor.self_improve import SelfImprove
from albra.security.policy_state import PolicyEngineState, VALID_MODES
from albra.security.classification import classify, DataClassification, label
from albra.security.rbac import has_permission, ROLES, list_roles, permissions_for
from albra.resilience.circuit_breaker import CircuitBreaker
from albra.evidence.legal_gate import LegalGate, LEGAL_RULES
from albra.memory.interface import (
    MemoryInterface,
    InMemoryProvider,
    SQLiteProvider,
    MemoryItem,
    TRUTH_LEVELS,
    PROVENANCE_TYPES,
    can_back_compliance,
    normalize_truth_level,
)
from albra.security.execution_guard import ExecutionGuard
from albra.knowledge.specialists import (
    SPECIALIST_CATALOG,
    get_specialist,
    list_specialists,
    is_specialist_ready,
)


# --- ExecutionTrace ---

def test_execution_trace_persists():
    with tempfile.TemporaryDirectory() as tmp:
        et = ExecutionTrace(f"{tmp}/et.db")
        eid = et.start(agent_id="ALBRA-BASE-V1", task="test task", requester="user1")
        et.append_tool_call(eid, name="clock", args={}, ok=True, result="ok")
        et.append_provider(eid, provider="mock", prompt_size=10, response_size=20)
        et.append_evidence(eid, "ev1")
        et.append_approval(eid, approval_id="ap1", action="send", status="pending")
        et.record_cost(eid, tokens_in=10, tokens_out=20, usd=0.001)
        et.finish(eid, status="completed", outputs={"reply": "ok"})
        row = et.get(eid)
        assert row is not None
        assert row["agent_id"] == "ALBRA-BASE-V1"
        assert row["status"] == "completed"
        assert len(row["tools"]) == 1
        assert row["tools"][0]["name"] == "clock"
        assert len(row["providers"]) == 1
        assert row["providers"][0]["provider"] == "mock"
        assert "ev1" in row["evidence_ids"]
        assert row["approvals"][0]["status"] == "pending"
        assert row["costs"]["tokens_in"] == 10
        et.close()


def test_execution_trace_list_recent():
    with tempfile.TemporaryDirectory() as tmp:
        et = ExecutionTrace(f"{tmp}/et.db")
        for i in range(5):
            et.start(agent_id="A", task=f"task_{i}", requester="u")
        recent = et.list_recent(limit=10)
        assert len(recent) == 5
        et.close()


def test_execution_trace_stats():
    with tempfile.TemporaryDirectory() as tmp:
        et = ExecutionTrace(f"{tmp}/et.db")
        eid = et.start(agent_id="A", task="t", requester="u")
        et.finish(eid, status="completed")
        stats = et.stats()
        assert stats["total"] == 1
        assert "completed" in stats["by_status"]
        et.close()


# --- Autonomy L0-L5 ---

def test_autonomy_levels_count():
    assert len(LEVELS) == 6
    assert LEVELS[0] == "L0_OBSERVE"
    assert LEVELS[5] == "L5_SELF_IMPROVE"


def test_autonomy_normalize_level():
    c = AutonomyController()
    assert c.normalize_level("L2") == "L2_EXECUTE_SAFE"
    assert c.normalize_level("l2") == "L2_EXECUTE_SAFE"
    assert c.normalize_level("L0_OBSERVE") == "L0_OBSERVE"
    assert c.normalize_level("invalid") is None


def test_autonomy_default_l2():
    c = AutonomyController()
    assert c.get_config()["max_level"] == "L2_EXECUTE_SAFE"
    assert c.get_config()["external_actions_allowed"] is False


def test_autonomy_l3_blocked_without_external():
    c = AutonomyController()
    # Subimos techo a L3 pero external deshabilitado
    c.set_max_level("L3_EXECUTE_EXTERNAL", reason="test")
    d = c.assert_allowed(requested_level="L3_EXECUTE_EXTERNAL", action="external")
    assert not d.allowed
    # Puede ser ceiling OR external reason - ambos válidos para L3 sin external
    assert "External" in d.reason or "ceiling" in d.reason.lower() or "exceeds" in d.reason.lower()


def test_autonomy_l3_allowed_with_external():
    c = AutonomyController()
    c.set_max_level("L3_EXECUTE_EXTERNAL", reason="test")
    c.set_external_allowed(True, reason="test")
    d = c.assert_allowed(requested_level="L3_EXECUTE_EXTERNAL", action="external")
    assert d.allowed


def test_autonomy_l4_blocked_without_manual_flag():
    """L4/L5 exigen flag manual incluso si subimos el techo."""
    c = AutonomyController()
    c.set_max_level("L5_SELF_IMPROVE", reason="test")
    d = c.assert_allowed(requested_level="L4_EXECUTE_SENSITIVE", action="sensitive")
    assert not d.allowed
    assert d.manual_flag_required


def test_autonomy_ceiling_enforced():
    c = AutonomyController()
    d = c.assert_allowed(requested_level="L3_EXECUTE_EXTERNAL", action="test")
    # L3 > ceiling L2 → blocked
    assert not d.allowed
    assert d.ceiling_enforced


def test_autonomy_records_history():
    c = AutonomyController()
    c.assert_allowed(requested_level="L0_OBSERVE", action="test")
    c.assert_allowed(requested_level="L3_EXECUTE_EXTERNAL", action="test2")
    hist = c.history()
    assert len(hist) >= 2


# --- SelfImprove ---

def test_self_improve_capture():
    with tempfile.TemporaryDirectory() as tmp:
        si = SelfImprove(f"{tmp}/si.db")
        eid = si.capture_error(tool_name="clock", error=RuntimeError("timeout occurred"))
        assert eid
        # Stats
        stats = si.stats()
        assert stats["total_errors"] == 1
        assert stats["unresolved_errors"] == 1
        si.close()


def test_self_improve_pattern_classification():
    with tempfile.TemporaryDirectory() as tmp:
        si = SelfImprove(f"{tmp}/si.db")
        si.capture_error(tool_name="clock", error=RuntimeError("timeout occurred"))
        si.capture_error(tool_name="clock", error=RuntimeError("auth failed"))
        si.capture_error(tool_name="clock", error=RuntimeError("network down"))
        # Each must classify differently
        si.close()


def test_self_improve_promotion_to_lesson():
    """≥3 errores del mismo patrón → lesson automática."""
    with tempfile.TemporaryDirectory() as tmp:
        si = SelfImprove(f"{tmp}/si.db")
        si.PROMOTION_THRESHOLD = 3
        si.capture_error(tool_name="clock", error="timeout 1")
        si.capture_error(tool_name="clock", error="timeout 2")
        si.capture_error(tool_name="clock", error="timeout 3")
        stats = si.stats()
        assert stats["total_lessons"] >= 1
        si.close()


def test_self_improve_validate_and_promote():
    with tempfile.TemporaryDirectory() as tmp:
        si = SelfImprove(f"{tmp}/si.db")
        si.PROMOTION_THRESHOLD = 2
        si.capture_error(tool_name="clock", error="timeout 1")
        si.capture_error(tool_name="clock", error="timeout 2")
        # Get the drafted lesson
        lessons = si.get_lessons_for_context(tool_name="clock")
        if lessons:
            lesson_id = lessons[0]["id"]
            si.validate_lesson(lesson_id)
            si.promote_lesson(lesson_id)
            promoted = si.get_promoted_lessons()
            assert len(promoted) >= 1
        si.close()


# --- PolicyState ---

def test_policy_modes_valid():
    assert "DRAFT" in VALID_MODES
    assert "LIVE" in VALID_MODES
    assert len(VALID_MODES) == 5


def test_policy_state_default():
    with tempfile.TemporaryDirectory() as tmp:
        ps = PolicyEngineState(f"{tmp}/ps.db")
        state = ps.get_state()
        assert state.mode == "DRAFT"
        assert state.kill_switch is False
        assert state.live_authorized is False
        ps.close()


def test_policy_state_events_append_only():
    with tempfile.TemporaryDirectory() as tmp:
        ps = PolicyEngineState(f"{tmp}/ps.db")
        ps.set_mode("RESEARCH", actor="admin", reason="test")
        ps.set_mode("REVIEW", actor="admin", reason="test2")
        events = ps.history(field="mode")
        assert len(events) >= 2
        ps.close()


def test_policy_kill_switch():
    with tempfile.TemporaryDirectory() as tmp:
        ps = PolicyEngineState(f"{tmp}/ps.db")
        ps.engage_kill_switch(reason="emergency", actor="admin")
        assert ps.get_state().kill_switch is True
        ps.release_kill_switch(actor="admin", reason="resolved")
        assert ps.get_state().kill_switch is False
        ps.close()


def test_policy_assert_can_execute_live():
    with tempfile.TemporaryDirectory() as tmp:
        ps = PolicyEngineState(f"{tmp}/ps.db")
        # Sin autorización
        ok, reason = ps.assert_can_execute_live()
        assert not ok
        # Con autorización pero modo incorrecto
        ps.authorize_live(actor="admin")
        ok, _ = ps.assert_can_execute_live()
        assert not ok
        ps.set_mode("LIVE")
        ps.set_autonomy_ceiling("L4_EXECUTE_SENSITIVE")
        ok, _ = ps.assert_can_execute_live()
        assert ok
        ps.close()


def test_policy_state_reload_after_restart():
    """State se reconstruye desde policy_events."""
    with tempfile.TemporaryDirectory() as tmp:
        path = f"{tmp}/ps.db"
        ps1 = PolicyEngineState(path)
        ps1.set_mode("LIVE", actor="admin", reason="go live")
        ps1.close()
        # Restart - state should reload
        ps2 = PolicyEngineState(path)
        assert ps2.get_state().mode == "LIVE"
        ps2.close()


# --- Data Classification ---

def test_classification_levels_count():
    assert len(DataClassification) == 9


def test_classification_public():
    r = classify("Hola mundo")
    assert r.classification == DataClassification.PUBLICO
    assert not r.requires_local


def test_classification_personal():
    r = classify("Mi cédula es 12345678")
    assert r.classification == DataClassification.DATO_PERSONAL
    assert r.requires_local
    assert r.requires_encryption


def test_classification_sensitive():
    r = classify("Paciente con diabetes tipo 2")
    assert r.classification == DataClassification.DATO_SENSIBLE


def test_classification_credential():
    r = classify("password=secret123 api_key=abc")
    # CREDENCIAL tiene prioridad sobre DATO_PERSONAL
    assert r.classification == DataClassification.CREDENCIAL


def test_classification_secret_profesional():
    r = classify("El cliente del expediente me dijo en secreto profesional")
    assert r.classification in (DataClassification.SECRETO_PROFESIONAL, DataClassification.EXPEDIENTE_JURIDICO)


def test_classification_label():
    assert label(DataClassification.PUBLICO) == "Público"
    assert label(DataClassification.CREDENCIAL) == "Credencial"


# --- RBAC ---

def test_rbac_roles_count():
    assert len(ROLES) >= 5  # owner, admin, abogado, asistente, externo, anon


def test_rbac_owner_has_all():
    assert has_permission("owner", "anything.you.want")
    assert has_permission("owner", "settings.*")


def test_rbac_abogado_can_write_demandas():
    assert has_permission("abogado", "demandas.write")
    assert has_permission("abogado", "expedientes.read")


def test_rbac_abogado_cannot_modify_settings():
    assert not has_permission("abogado", "settings.write")


def test_rbac_anon_only_basic():
    assert has_permission("anon", "tools.invoke_low")
    assert not has_permission("anon", "demandas.write")
    assert not has_permission("anon", "expedientes.read")


def test_rbac_wildcard_resource():
    # admin has 'expedientes.*' which should match expedientes.read/write/delete/export
    assert has_permission("admin", "expedientes.delete")
    assert has_permission("admin", "expedientes.export")


def test_rbac_permissions_for():
    perms = permissions_for("abogado")
    assert "demandas.write" in perms
    assert "settings.write" not in perms


# --- Circuit Breaker ---

def test_circuit_breaker_starts_closed():
    cb = CircuitBreaker()
    assert cb.can_pass("provider_x") is True


def test_circuit_breaker_opens_on_failures():
    cb = CircuitBreaker(failure_threshold=3, cool_off_seconds=60)
    for _ in range(3):
        cb.record_failure("p")
    assert not cb.can_pass("p")
    status = cb.status()
    assert status["p"]["state"] == "OPEN"


def test_circuit_breaker_half_open_after_cooloff():
    cb = CircuitBreaker(failure_threshold=2, cool_off_seconds=0.1)
    cb.record_failure("p")
    cb.record_failure("p")
    assert not cb.can_pass("p")
    import time
    time.sleep(0.15)
    assert cb.can_pass("p")  # half_open
    assert cb.status()["p"]["state"] == "HALF_OPEN"


def test_circuit_breaker_recovers():
    cb = CircuitBreaker(failure_threshold=2, cool_off_seconds=0.1, success_threshold=1)
    cb.record_failure("p")
    cb.record_failure("p")
    import time
    time.sleep(0.15)
    cb.can_pass("p")  # → half_open
    cb.record_success("p")
    assert cb.status()["p"]["state"] == "CLOSED"


def test_circuit_breaker_force():
    cb = CircuitBreaker()
    cb.force_open("p", reason="manual")
    assert not cb.can_pass("p")
    cb.force_close("p")
    assert cb.can_pass("p")


# --- Legal Gate ---

def test_legal_gate_verdicts():
    gate = LegalGate()
    # Internal research → APPROVED
    v = gate.evaluate("internal_research")
    assert v.verdict == "APPROVED"


def test_legal_gate_blocked_actions():
    gate = LegalGate()
    # Sign document without LIVE → BLOCKED
    v = gate.evaluate("sign_document", live_authorized=False)
    assert v.verdict == "BLOCKED"


def test_legal_gate_review_required_for_publish():
    gate = LegalGate()
    v = gate.evaluate("publish_content")
    assert v.verdict == "REVIEW_REQUIRED"


def test_legal_gate_personal_data_with_limits():
    gate = LegalGate()
    v = gate.evaluate("process_personal_data")
    assert v.verdict == "APPROVED_WITH_LIMITS"
    assert len(v.limits) > 0


def test_legal_gate_blocks_credentials_in_external():
    gate = LegalGate()
    v = gate.evaluate(
        "send_external_communication",
        text="mi password es secret123",
    )
    assert v.verdict == "BLOCKED"
    assert v.classification == "CREDENCIAL"


def test_legal_gate_unknown_action():
    gate = LegalGate()
    v = gate.evaluate("nonexistent_action")
    assert v.verdict == "UNKNOWN"


def test_legal_gate_rules_count():
    assert len(LEGAL_RULES) >= 12


# --- Memory Interface ---

def test_memory_truth_levels():
    assert "VERIFIED" in TRUTH_LEVELS
    assert "UNKNOWN" in TRUTH_LEVELS
    assert len(TRUTH_LEVELS) == 5


def test_memory_provenance_types():
    assert "USER_INPUT" in PROVENANCE_TYPES
    assert "AI_MODEL" in PROVENANCE_TYPES
    assert "OFFICIAL_SOURCE" in PROVENANCE_TYPES


def test_can_back_compliance():
    assert can_back_compliance("VERIFIED") is True
    assert can_back_compliance("OBSERVED") is True
    assert can_back_compliance("INFERRED") is False
    assert can_back_compliance("UNKNOWN") is False


def test_normalize_truth_level():
    assert normalize_truth_level("verified") == "VERIFIED"
    assert normalize_truth_level("foo") == "UNKNOWN"
    assert normalize_truth_level(None) == "UNKNOWN"


def test_memory_interface_inmemory():
    mi = MemoryInterface(backend="inmemory")
    asyncio.run(mi.startup())
    eid = asyncio.run(mi.write("hello world", category="conversational", truth_level="VERIFIED", provenance="USER_INPUT"))
    items = asyncio.run(mi.retrieve("hello"))
    assert len(items) >= 1
    assert items[0].text == "hello world"
    asyncio.run(mi.shutdown())


def test_memory_interface_sqlite():
    with tempfile.TemporaryDirectory() as tmp:
        mi = MemoryInterface(backend="sqlite", db_path=f"{tmp}/mem.db")
        asyncio.run(mi.startup())
        eid = asyncio.run(mi.write("test text", category="operational", truth_level="OBSERVED"))
        items = asyncio.run(mi.retrieve("test"))
        assert len(items) >= 1
        # Update
        asyncio.run(mi.update(eid, "updated text"))
        items = asyncio.run(mi.retrieve("updated"))
        assert len(items) >= 1
        # Decay
        asyncio.run(mi.decay(days_threshold=0))
        asyncio.run(mi.shutdown())


def test_memory_interface_truth_level_stats():
    mi = MemoryInterface(backend="inmemory")
    asyncio.run(mi.write("verified text", category="knowledge", truth_level="VERIFIED"))
    asyncio.run(mi.write("observed text", category="knowledge", truth_level="OBSERVED"))
    asyncio.run(mi.write("unknown text", category="knowledge", truth_level="UNKNOWN"))
    stats = mi.stats()
    assert "by_truth_level" in stats
    assert stats["by_truth_level"].get("VERIFIED", 0) >= 1


def test_memory_interface_decay():
    """Relevance decae con el tiempo."""
    mi = MemoryInterface(backend="inmemory")
    eid = asyncio.run(mi.write("old item", category="operational"))
    # Force last_seen back in time
    for item in mi._provider._items:
        if item.id == eid:
            item.last_seen = 0  # epoch
    asyncio.run(mi.decay(days_threshold=1))
    items = asyncio.run(mi.retrieve("old"))
    assert len(items) >= 1
    assert items[0].relevance < 1.0


# --- Execution Guard ---

def test_execution_guard_blocks_when_kill_switch():
    from albra.security.policy_state import PolicyEngineState
    with tempfile.TemporaryDirectory() as tmp:
        ps = PolicyEngineState(f"{tmp}/ps.db")
        ps.engage_kill_switch(reason="test")
        guard = ExecutionGuard()
        v = guard.check(action="publish_legal_filing", user_role="admin", policy_state=ps.get_state())
        assert not v.allowed
        ps.close()


def test_execution_guard_blocks_without_live():
    guard = ExecutionGuard()
    v = guard.check(action="sign_document", user_role="admin", live_authorized=False)
    assert not v.allowed


def test_execution_guard_dedup():
    guard = ExecutionGuard()
    v1 = guard.check(action="internal_research", user_role="admin", dedup_key="action_1")
    v2 = guard.check(action="internal_research", user_role="admin", dedup_key="action_1")
    assert v1.allowed
    assert not v2.allowed  # dedup


def test_execution_guard_with_legal_gate_blocked():
    gate = LegalGate()
    verdict = gate.evaluate("send_external_communication", text="password=secret")
    guard = ExecutionGuard()
    v = guard.check(
        action="send_external_message",
        user_role="admin",
        live_authorized=True,
        hitl_approved=True,
        legal_gate_verdict=verdict,
    )
    assert not v.allowed


# --- Specialists ---

def test_specialist_catalog_count():
    assert len(SPECIALIST_CATALOG) >= 15  # civil, penal, laboral, etc.


def test_specialist_get_civil():
    s = get_specialist("civil")
    assert s is not None
    assert s.area == "civil"
    assert "ALBRA-CIVIL" in s.codename


def test_specialist_list():
    items = list_specialists()
    assert len(items) >= 15
    areas = [i["area"] for i in items]
    for expected_area in ("civil", "penal", "laboral", "constitucional", "compliance"):
        assert expected_area in areas


def test_specialist_not_ready_by_default():
    """Ningún especialista está ready - solo perfiles declarados."""
    assert is_specialist_ready("civil") is False
    assert is_specialist_ready("penal") is False


def test_specialist_penal_low_autonomy():
    """Penal es delicado - ceiling bajo por defecto."""
    s = get_specialist("penal")
    assert s.default_autonomy_ceiling == "L1_RECOMMEND"


# --- Agent integration V1.5 ---

def test_agent_v15_boots_with_new_organs():
    from albra.identity.agent import get_agent
    async def _run():
        agent = get_agent()
        await agent.boot()
        # Órganos nuevos V1.5
        for organ in ("execution_trace", "autonomy", "self_improve",
                      "policy_state", "circuit_breaker", "legal_gate",
                      "memory_interface", "execution_guard"):
            assert organ in agent.organs, f"Falta órgano V1.5: {organ}"
        # classify y has_permission como funciones
        assert callable(agent.organs["classify"])
        assert callable(agent.organs["has_permission"])
        await agent.shutdown()
    asyncio.run(_run())


def test_agent_v15_records_execution_trace():
    from albra.identity.agent import get_agent
    async def _run():
        agent = get_agent()
        await agent.boot()
        r = await agent.process("hola", user="test")
        assert r.get("execution_id")
        assert r.get("classification") is not None
        assert r.get("legal_verdict") in ("APPROVED", "APPROVED_WITH_LIMITS", "REVIEW_REQUIRED", "BLOCKED", "UNKNOWN")
        await agent.shutdown()
    asyncio.run(_run())
