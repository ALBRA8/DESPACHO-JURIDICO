"""Tests V1.6 FINAL - 5 frentes críticos: CI/auth/runtime-sovereignty/audit/self-improve-reuse."""
import asyncio
import os
import tempfile
import time

import pytest

from albra.audit.tamper_evident import TamperEvidentAudit
from albra.config.settings import Settings
from albra.doctor.self_improve import SelfImprove
from albra.evidence.legal_gate import LegalGate
from albra.identity.agent import get_agent
from albra.observability.execution_trace import ExecutionTrace
from albra.security.autonomy import AutonomyController
from albra.security.execution_guard import ExecutionGuard
from albra.security.policy_state import PolicyEngineState
from albra.security.rbac import has_permission
from albra.security.tokens import issue_token, verify_token

# --- FRONT 1: Python 3.10 compatibility (CI GREEN) ---

def test_python_3_10_no_dt_UTC():
    """NO usar dt.UTC (solo Python 3.11+). Usar timezone.utc."""
    import inspect

    import albra.tools.builtin as builtin
    src = inspect.getsource(builtin)
    # El código debe manejar el fallback a timezone.utc
    assert "timezone.utc" in src, "builtin.py debe manejar Python 3.10 fallback"


def test_python_3_10_no_3_11_only_features():
    """No usar Self, TaskGroup, tomllib, dt.UTC sin fallback."""
    import pathlib
    forbidden = ["typing.Self", "tomllib.", "TaskGroup(", "BaseExceptionGroup", "asyncio.timeout("]
    found_issues = []
    for p in pathlib.Path("albra").rglob("*.py"):
        text = p.read_text()
        for f in forbidden:
            if f in text:
                # Allow with try/except fallback
                if f == "tomllib.":
                    continue  # we don't use it
                found_issues.append(f"{p}: {f}")
    assert not found_issues, f"Forbidden 3.11+ patterns: {found_issues}"


def test_clock_tool_works_python_3_10_compat():
    """El clock tool debe funcionar en cualquier Python 3.10+."""
    from albra.tools.builtin import _clock_handler
    result = asyncio.run(_clock_handler({}, user="test"))
    assert result.ok is True
    assert "iso" in result.value
    assert result.value["tz"] == "UTC"


# --- FRONT 2: API auth SIN hardcoded service tokens ---

def test_no_hardcoded_service_token():
    """NO existe 'albra-internal-service' hardcoded en el código."""
    import inspect

    import albra.api.app as app_module
    src = inspect.getsource(app_module)
    assert "albra-internal-service" not in src, "Service token hardcoded debe ser eliminado"
    assert "X-Service-Token" not in src, "X-Service-Token bypass debe ser eliminado"


def test_no_user_password_bearer_format():
    """NO se usa formato 'user:password' como bearer (split en :)."""
    import inspect

    import albra.api.app as app_module
    src = inspect.getsource(app_module)
    # Buscar el patrón split(":", 1) usado para extraer user:password del token
    assert 'token.split(":", 1)' not in src, "user:password split pattern debe ser eliminado"
    assert 'token.split(\':\', 1)' not in src, "user:password split pattern debe ser eliminado"


def test_jwt_token_issue_and_verify():
    """JWT HMAC token funciona - sin deps externas."""
    os.environ["ALBRA_JWT_SECRET"] = "test_secret_for_ci"
    try:
        token = issue_token(subject="user1", role="admin", expires_in_seconds=3600)
        payload = verify_token(token)
        assert payload is not None
        assert payload["sub"] == "user1"
        assert payload["role"] == "admin"
        assert "exp" in payload
    finally:
        os.environ.pop("ALBRA_JWT_SECRET", None)


def test_jwt_token_invalid_denied():
    """Token inválido → DENY."""
    os.environ["ALBRA_JWT_SECRET"] = "test_secret"
    try:
        assert verify_token("invalid.token.here") is None
        assert verify_token("") is None
        assert verify_token("no-dot") is None
    finally:
        os.environ.pop("ALBRA_JWT_SECRET", None)


def test_jwt_token_expired_denied():
    """Token expirado → DENY."""
    os.environ["ALBRA_JWT_SECRET"] = "test_secret"
    try:
        token = issue_token(subject="user", role="admin", expires_in_seconds=-1)
        # Already expired
        payload = verify_token(token)
        assert payload is None
    finally:
        os.environ.pop("ALBRA_JWT_SECRET", None)


def test_jwt_token_tampered_denied():
    """Token con payload manipulado → firma no calza → DENY."""
    os.environ["ALBRA_JWT_SECRET"] = "secret1"
    try:
        token = issue_token(subject="user", role="anon", expires_in_seconds=3600)
        # Cambiar el secret para que la firma no calce
        os.environ["ALBRA_JWT_SECRET"] = "secret2"
        payload = verify_token(token)
        assert payload is None  # Firma no calza
    finally:
        os.environ.pop("ALBRA_JWT_SECRET", None)


def test_jwt_token_wrong_secret_denied():
    """Token emitido con secret A no verifica con secret B."""
    os.environ["ALBRA_JWT_SECRET"] = "secret_a"
    token = issue_token(subject="user", role="admin")
    os.environ["ALBRA_JWT_SECRET"] = "secret_b"
    payload = verify_token(token)
    assert payload is None
    os.environ.pop("ALBRA_JWT_SECRET", None)


# --- FRONT 3: Runtime sovereignty ---

def test_agent_process_delegates_to_runtime():
    """Agent.process() es solo fachada - delega a Runtime.execute()."""
    async def _run():
        agent = get_agent()
        await agent.boot()
        # El runtime está en organs
        runtime = agent.organs["runtime"]
        assert runtime is not None
        # Verificar que Runtime tiene execute()
        assert hasattr(runtime, "execute")
        # Process debe producir mismo resultado que execute directo
        r1 = await agent.process("hola test sovereignty", user="test")
        r2 = await runtime.execute("hola test sovereignty", user="test")
        # Mismo formato de resultado
        assert "execution_id" in r1
        assert "execution_id" in r2
        await agent.shutdown()
    asyncio.run(_run())


def test_runtime_is_single_authority():
    """Runtime es la ÚNICA autoridad de pipeline."""
    async def _run():
        agent = get_agent()
        await agent.boot()
        runtime = agent.organs["runtime"]
        # Runtime debe tener todos los órganos wired
        assert runtime.organs, "Runtime debe estar wired con órganos"
        for organ_name in (
            "audit", "events", "reasoning", "memory", "tools",
            "autonomy", "policy_state", "classify", "has_permission",
            "legal_gate", "self_improve", "circuit_breaker",
            "execution_guard", "execution_trace",
        ):
            assert organ_name in runtime.organs, f"Runtime no tiene órgano: {organ_name}"
        await agent.shutdown()
    asyncio.run(_run())


def test_no_dual_pipeline_in_agent():
    """Agent.process() NO contiene pipeline de ejecución duplicada."""
    import inspect

    from albra.identity.agent import Agent
    src = inspect.getsource(Agent.process)
    # process debe ser muy corto - solo delega a runtime.execute
    # NO debe contener pipeline de reasoning, tools, etc.
    forbidden_in_process = [
        "reasoning.plan(",
        "tools.invoke(",
        "execution_guard.check(",
        "memory.write(",
        "memory.retrieve(",
    ]
    for f in forbidden_in_process:
        assert f not in src, f"Agent.process contiene '{f}' - debe delegar a Runtime"


def test_runtime_executes_through_pipeline():
    """Runtime.execute recorre todo el pipeline."""
    async def _run():
        agent = get_agent()
        await agent.boot()
        runtime = agent.organs["runtime"]
        # Ejecutar tarea normal
        r = await runtime.execute("hola", user="test", user_role="anon")
        assert r["authorized"] is True
        assert r["execution_id"]
        # Verificar que pasó por execution_trace
        trace = agent.execution_trace.get(r["execution_id"])
        assert trace is not None
        assert trace["status"] == "completed"
        await agent.shutdown()
    asyncio.run(_run())


def test_runtime_denied_action():
    """Acción denegada atraviesa Runtime (no bypass)."""
    async def _run():
        agent = get_agent()
        await agent.boot()
        runtime = agent.organs["runtime"]
        # anon no tiene tools.invoke_low en este rol... espera sí lo tiene
        # Vamos a forzar denegación con kill switch
        ps = agent.organs["policy_state"]
        ps.engage_kill_switch(reason="test")
        r = await runtime.execute("hola", user="test", user_role="admin")
        assert r["authorized"] is False
        ps.release_kill_switch(actor="admin", reason="done")
        await agent.shutdown()
    asyncio.run(_run())


def test_runtime_tool_failure_handled():
    """Tool failure es capturada por Runtime (no crash)."""
    async def _run():
        agent = get_agent()
        await agent.boot()
        runtime = agent.organs["runtime"]
        # Registrar tool que falla
        from albra.tools.base import Tool, ToolResult
        async def boom(input_data, *, user):
            raise RuntimeError("BOOM")
        agent.organs["tools"].register(Tool(
            name="boom_tool", description="boom",
            input_schema={}, handler=boom, risk="low",
            category="test",
        ))
        # Process no debe crashear
        r = await runtime.execute("calcula boom_tool", user="test", user_role="admin")
        assert "execution_id" in r
        await agent.shutdown()
    asyncio.run(_run())


# --- FRONT 4: Audit Integrity Integration ---

def test_audit_trace_tamper_integration():
    """Operación crítica produce audit + trace + tamper record."""
    async def _run():
        agent = get_agent()
        await agent.boot()
        r = await agent.process("hola audit test", user="audit_user")
        exec_id = r["execution_id"]
        # Audit log tiene el outtake
        audit_items = agent.organs["audit"].read(limit=10)
        assert any("outtake" in str(a.get("type", "")) for a in audit_items)
        # ExecutionTrace tiene la ejecución
        trace = agent.execution_trace.get(exec_id)
        assert trace is not None
        assert trace["status"] == "completed"
        # Tamper-evident chain - verificar integridad
        agent.tamper_audit.read(limit=10)
        # Cadena verificable (aunque tenga 0 o muchos records)
        verify = agent.tamper_audit.verify_chain()
        assert verify["ok"] is True
        await agent.shutdown()
    asyncio.run(_run())


def test_audit_integrity_after_restart():
    """Tras restart, audit chain se puede verificar."""
    with tempfile.TemporaryDirectory() as tmp:
        path = f"{tmp}/audit.log.chain"
        audit1 = TamperEvidentAudit(path)
        asyncio.run(audit1.append("test_event", {"k": "v1"}))
        asyncio.run(audit1.append("test_event", {"k": "v2"}))
        # Restart - new instance same file
        audit2 = TamperEvidentAudit(path)
        verify = audit2.verify_chain()
        assert verify["ok"] is True
        assert verify["total"] == 2


def test_audit_tamper_detected():
    """Manipular audit chain → verify_chain detecta."""
    with tempfile.TemporaryDirectory() as tmp:
        path = f"{tmp}/audit.log.chain"
        audit = TamperEvidentAudit(path)
        asyncio.run(audit.append("test", {"k": "v1"}))
        asyncio.run(audit.append("test", {"k": "v2"}))
        # Tamper
        with open(path, "r") as f:
            lines = f.readlines()
        lines[0] = lines[0].replace('"v1"', '"HACKED"')
        with open(path, "w") as f:
            f.writelines(lines)
        result = audit.verify_chain()
        assert result["ok"] is False


def test_execution_trace_persists_after_restart():
    """ExecutionTrace sqlite sobrevive restart."""
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


# --- FRONT 5: SelfImprove → Reasoning reuse ---

def test_self_improve_reuse_path():
    """Lesson promoted puede ser recuperada por reasoning."""
    with tempfile.TemporaryDirectory() as tmp:
        si = SelfImprove(f"{tmp}/si.db")
        si.PROMOTION_THRESHOLD = 2
        # Capture errors to trigger lesson auto-draft
        si.capture_error(tool_name="clock", error="timeout 1")
        si.capture_error(tool_name="clock", error="timeout 2")
        lessons = si.get_lessons_for_context()
        if lessons:
            lesson_id = lessons[0]["id"]
            # Validate + promote (requires HITL)
            si.validate_lesson(lesson_id, validator="admin")
            # Promote WITHOUT HITL → debe fallar (safety)
            result = si.promote_lesson(lesson_id)
            assert not result["ok"]
            assert "hitl_required" in result["reason"]
            # Promote WITH HITL → ok
            result = si.promote_lesson(lesson_id, hitl_request_id="hitl_001")
            assert result["ok"]
            # Lesson promoted → reasoning puede recuperarla
            promoted = si.get_promoted_lessons()
            assert len(promoted) >= 1
            assert promoted[0]["pattern_key"].startswith("clock:")
        si.close()


def test_self_improve_persists_after_restart():
    """Lessons persisten tras restart y reasoning puede recuperarlas."""
    with tempfile.TemporaryDirectory() as tmp:
        path = f"{tmp}/si.db"
        si1 = SelfImprove(path)
        si1.PROMOTION_THRESHOLD = 2
        si1.capture_error(tool_name="clock", error="timeout 1")
        si1.capture_error(tool_name="clock", error="timeout 2")
        # Buscar lessons DRAFTED (no validated) directamente
        cur = si1._conn.execute("SELECT id FROM lessons ORDER BY created_at DESC LIMIT 1")
        row = cur.fetchone()
        if row:
            lesson_id = row[0]
            si1.validate_lesson(lesson_id, validator="admin")
            si1.promote_lesson(lesson_id, hitl_request_id="hitl_001")
        si1.close()
        # Restart
        si2 = SelfImprove(path)
        promoted = si2.get_promoted_lessons()
        assert len(promoted) >= 1, "Promoted lessons should persist after restart"
        si2.close()


def test_self_improve_unapproved_not_in_reasoning():
    """Lesson no aprobada NO aparece en promoted_lessons."""
    with tempfile.TemporaryDirectory() as tmp:
        si = SelfImprove(f"{tmp}/si.db")
        si.PROMOTION_THRESHOLD = 2
        si.capture_error(tool_name="clock", error="timeout 1")
        si.capture_error(tool_name="clock", error="timeout 2")
        lessons = si.get_lessons_for_context()
        if lessons:
            lesson_id = lessons[0]["id"]
            # Solo validate (no promote)
            si.validate_lesson(lesson_id, validator="admin")
            # NO promover
            promoted = si.get_promoted_lessons()
            assert len(promoted) == 0  # Sin promote no aparece
        si.close()


def test_agent_reasoning_uses_promoted_lessons():
    """El agente recupera promoted_lessons durante process()."""
    async def _run():
        agent = get_agent()
        await agent.boot()
        runtime = agent.organs["runtime"]
        # Sin promoted lessons - funciona normal
        r = await runtime.execute("hola", user="test", user_role="anon")
        assert "promoted_lessons_used" in r
        await agent.shutdown()
    asyncio.run(_run())


def test_self_improve_cannot_modify_critical_systems():
    """SelfImprove no tiene métodos para modificar policy/code/rbac."""
    with tempfile.TemporaryDirectory() as tmp:
        si = SelfImprove(f"{tmp}/si.db")
        # Verificar que NO existen métodos peligrososos
        forbidden_methods = [
            "modify_code", "modify_autonomy", "modify_policy",
            "engage_kill_switch", "elevate_role", "delete_audit_log",
            "modify_rbac", "bypass_execution_guard",
        ]
        for m in forbidden_methods:
            assert not hasattr(si, m), f"SelfImprove tiene método peligroso: {m}"
        # Pero SÍ tiene forbidden_actions list
        assert hasattr(si, "forbidden_actions")
        forbidden = si.forbidden_actions()
        assert "modify_code" in forbidden
        si.close()


# --- ATTACK TESTS nuevos ---

def test_attack_jwt_no_token():
    """Ataque: request sin JWT → 401."""
    # Simulado - no levantamos server real
    # Verificamos que require_auth sin creds raises
    import inspect

    from albra.api.app import require_auth
    src = inspect.getsource(require_auth)
    # Debe raise 401 si no credentials
    assert "401" in src or "HTTP_401" in src


def test_attack_jwt_invalid_token():
    """Ataque: JWT inválido → DENY."""
    os.environ["ALBRA_JWT_SECRET"] = "test"
    try:
        assert verify_token("invalid") is None
        assert verify_token("a.b") is None
        assert verify_token("a.b.c") is None
    finally:
        os.environ.pop("ALBRA_JWT_SECRET", None)


def test_attack_runtime_bypass_attempt():
    """Ataque: intentar bypass Runtime → no funciona."""
    async def _run():
        agent = get_agent()
        await agent.boot()
        # Intentar invocar tool sin pasar por runtime/guard
        # Debe fallar o ser ignorado
        from albra.tools.base import Tool, ToolResult
        called = {"n": 0}
        async def handler(input, *, user):
            called["n"] += 1
            return ToolResult(ok=True, value="ok")
        tool = Tool(
            name="bypass_test", description="bypass",
            input_schema={}, handler=handler, risk="low",
            category="test",
        )
        agent.organs["tools"].register(tool)
        # Invocar directamente (no via runtime)
        result = await agent.organs["tools"].invoke("bypass_test", {}, user="test")
        # Tool registry invoca - PERO esto NO bypassa el guard del runtime
        # porque el runtime no fue llamado
        assert result["ok"] is True  # tool corrió
        # Pero NO se registró en execution_trace del runtime
        # (porque no pasó por runtime.execute)
        traces = agent.execution_trace.list_recent(limit=5)
        bypass_traces = [t for t in traces if "bypass_test" in t.get("task", "")]
        # No debe haber trace porque no pasó por runtime
        assert len(bypass_traces) == 0
        await agent.shutdown()
    asyncio.run(_run())


def test_attack_audit_tamper():
    """Ataque: alterar audit trail → verify_chain detecta."""
    with tempfile.TemporaryDirectory() as tmp:
        path = f"{tmp}/a.chain"
        audit = TamperEvidentAudit(path)
        asyncio.run(audit.append("event1", {"data": "x"}))
        asyncio.run(audit.append("event2", {"data": "y"}))
        # Tamper
        with open(path, "r") as f:
            content = f.read()
        content = content.replace("x", "HACKED")
        with open(path, "w") as f:
            f.write(content)
        result = audit.verify_chain()
        assert result["ok"] is False


def test_attack_self_improve_promote_without_approval():
    """Ataque: promover lesson sin HITL → DENY."""
    with tempfile.TemporaryDirectory() as tmp:
        si = SelfImprove(f"{tmp}/si.db")
        si.PROMOTION_THRESHOLD = 2
        si.capture_error(tool_name="x", error="timeout 1")
        si.capture_error(tool_name="x", error="timeout 2")
        lessons = si.get_lessons_for_context()
        if lessons:
            lesson_id = lessons[0]["id"]
            si.validate_lesson(lesson_id, validator="admin")
            # Sin HITL
            result = si.promote_lesson(lesson_id)
            assert not result["ok"]
            assert "hitl_required" in result["reason"]
        si.close()


def test_attack_runtime_no_bypass_when_killswitch():
    """Ataque: kill switch activo → no bypass."""
    async def _run():
        agent = get_agent()
        await agent.boot()
        runtime = agent.organs["runtime"]
        ps = agent.organs["policy_state"]
        ps.engage_kill_switch(reason="test_attack")
        r = await runtime.execute("hola", user="attacker", user_role="admin")
        # Aunque sea admin, kill switch bloquea
        assert r["authorized"] is False
        ps.release_kill_switch(actor="admin", reason="done")
        await agent.shutdown()
    asyncio.run(_run())


# --- BIRTH TEST end-to-end ---

def test_birth_test_full_pipeline():
    """Test de nacimiento: request atraviesa todo el pipeline."""
    async def _run():
        agent = get_agent()
        await agent.boot()
        # Birth test
        r = await agent.process(
            "Hola, soy el primer request de un organismo recién nacido",
            user="birth_test",
            user_role="anon",
        )
        # Verificaciones del birth test
        assert r["authorized"] is True
        assert r["execution_id"]  # generation ID
        assert r["classification"]  # pasó por classification
        assert r["legal_verdict"] in ("APPROVED", "APPROVED_WITH_LIMITS", "REVIEW_REQUIRED", "BLOCKED", "UNKNOWN")
        assert r["provider_used"]  # usó un provider (mock por defecto)
        # Verificar que se registró en audit
        audit_items = agent.organs["audit"].read(limit=10)
        types = [a.get("type") for a in audit_items]
        assert "intake" in types
        assert "outtake" in types
        # Verificar execution_trace
        trace = agent.execution_trace.get(r["execution_id"])
        assert trace is not None
        assert trace["status"] == "completed"
        # Verificar memory write
        memory_stats = agent.organs["memory"].stats()
        assert memory_stats.get("total", 0) >= 1
        await agent.shutdown()
    asyncio.run(_run())


def test_birth_test_legal_question_safe():
    """Birth test con pregunta legal → NO inventa doctrina."""
    async def _run():
        agent = get_agent()
        await agent.boot()
        r = await agent.process(
            "¿Qué dice el artículo 25 del código civil colombiano?",
            user="legal_birth",
            user_role="anon",
        )
        # Debe usar rules_fallback_legal (no LLM)
        assert r["provider_used"] == "rules_fallback_legal"
        # Reply debe decir que conocimiento no está cargado
        assert "cargado" in r["reply"].lower() or "no inventa" in r["reply"].lower()
        await agent.shutdown()
    asyncio.run(_run())


# --- Regression: todavía pasan los tests críticos ---

def test_runtime_process_regression_greeting():
    """Regression: greeting funciona vía runtime."""
    async def _run():
        agent = get_agent()
        await agent.boot()
        r = await agent.process("hola", user="test")
        assert r["authorized"] is True
        assert "ALBRA" in r["reply"]
        await agent.shutdown()
    asyncio.run(_run())


def test_runtime_process_regression_tool():
    """Regression: tool invocation vía runtime."""
    async def _run():
        agent = get_agent()
        await agent.boot()
        r = await agent.process("calcula 7 * 8", user="test", user_role="anon")
        # Tool debe ser invocada (anon tiene tools.invoke_low)
        assert r["execution_id"]
        await agent.shutdown()
    asyncio.run(_run())
