"""Tests de doctor, seguridad, evidencia, workflows, providers, resiliencia, audit."""
import asyncio
import tempfile

from albra.audit.log import AuditLog
from albra.config.settings import Settings
from albra.doctor.diagnostic import Doctor
from albra.events.bus import EventBus
from albra.evidence.chain import EvidenceChain
from albra.providers.llm import MockLLMProvider
from albra.providers.registry import ProviderRegistry
from albra.resilience.fallback import FallbackChain
from albra.resilience.retry import RetryPolicy, retry
from albra.security.auth import SecurityGate
from albra.security.hitl import HITLGate
from albra.workflows.engine import TaskStatus, WorkflowEngine


def test_doctor_diagnose_returns_report():
    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings(memory_path=f"{tmp}/mem.db", audit_path=f"{tmp}/audit.log")
        doc = Doctor(settings)
        report = asyncio.run(doc.diagnose(scope="all"))
        summary = report.build_summary()
        assert summary["total"] > 0
        assert summary["ok"] >= 0


def test_doctor_detects_mock_provider():
    settings = Settings(default_provider="mock")
    doc = Doctor(settings)
    result = doc._check_providers()
    assert result.severity == "warn"
    assert "mock" in result.detail.lower()


def test_security_login_and_authorize():
    settings = Settings(admin_password="testpass")
    gate = SecurityGate(settings)
    # Login admin
    ctx = asyncio.run(gate.login("admin", "testpass"))
    assert ctx.authenticated is True
    assert ctx.role == "admin"
    # Authorize low-risk
    authz = asyncio.run(gate.authorize("admin", action="chat", risk="low"))
    assert authz.metadata.get("allowed") is True


def test_security_wrong_password_fails():
    settings = Settings()
    gate = SecurityGate(settings)
    ctx = asyncio.run(gate.login("admin", "wrong"))
    assert ctx.authenticated is False


def test_hitl_request_and_approve():
    settings = Settings()
    gate = HITLGate(settings)
    req = asyncio.run(gate.request_approval(
        user="test", action="send_external_message", risk="high"
    ))
    assert req.status == "pending"
    assert len(gate.pending()) == 1
    asyncio.run(gate.approve(req.id, by="admin"))
    assert gate.status(req.id) == "approved"


def test_hitl_deny():
    settings = Settings()
    gate = HITLGate(settings)
    req = asyncio.run(gate.request_approval(user="test", action="publish_document"))
    asyncio.run(gate.deny(req.id, by="admin", reason="test"))
    assert gate.status(req.id) == "denied"


def test_evidence_add_and_trace():
    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings(audit_path=f"{tmp}/audit.log")
        ev = EvidenceChain(settings)
        asyncio.run(ev.startup())
        eid = asyncio.run(ev.add(
            kind="research_finding",
            content="Test content",
            source="https://test.source",
        ))
        trace = ev.trace(eid)
        assert trace["id"] == eid
        assert trace["kind"] == "research_finding"
        asyncio.run(ev.shutdown())


def test_evidence_provenance_chain():
    """Soporta pipeline SOURCE → INGESTION → EXTRACTION → EVIDENCE → PROVENANCE → ANALYSIS → CONCLUSION → ACTION."""
    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings(audit_path=f"{tmp}/audit.log")
        ev = EvidenceChain(settings)
        src_id = asyncio.run(ev.add(kind="source", content="raw text", source="https://x"))
        ext_id = asyncio.run(ev.add(
            kind="extraction", content="extracted", source="https://x",
            depends_on=[src_id]
        ))
        trace = ev.trace(ext_id)
        assert trace["depends_on_items"][0]["id"] == src_id


def test_workflows_lifecycle():
    settings = Settings()
    bus = EventBus(settings)
    wf = WorkflowEngine(settings, event_bus=bus)
    t = asyncio.run(wf.create_task("test_task"))
    asyncio.run(wf.start(t.id))
    assert t.status == TaskStatus.RUNNING
    asyncio.run(wf.complete(t.id, result={"ok": True}))
    assert t.status == TaskStatus.SUCCEEDED
    assert t.result == {"ok": True}


def test_workflows_fail():
    settings = Settings()
    bus = EventBus(settings)
    wf = WorkflowEngine(settings, event_bus=bus)
    t = asyncio.run(wf.create_task("test"))
    asyncio.run(wf.start(t.id))
    asyncio.run(wf.fail(t.id, error="test error"))
    assert t.status == TaskStatus.FAILED
    assert t.error == "test error"


def test_providers_registry_defaults_to_mock():
    settings = Settings()
    reg = ProviderRegistry(settings)
    p = reg.get()
    assert p.name == "mock"


def test_mock_llm_responds():
    p = MockLLMProvider()
    r = asyncio.run(p.call("¿hola?"))
    assert r.ok is True
    assert "MOCK" in r.text


def test_retry_decorator():
    counter = {"n": 0}

    @retry(RetryPolicy(max_attempts=3, base_delay=0.01))
    async def flaky():
        counter["n"] += 1
        if counter["n"] < 3:
            raise RuntimeError("flaky fail")
        return "ok"

    result = asyncio.run(flaky())
    assert result == "ok"
    assert counter["n"] == 3


def test_fallback_chain():
    chain = FallbackChain()

    async def a():
        raise RuntimeError("A failed")

    async def b():
        return "B ok"

    chain.add("A", a)
    chain.add("B", b)
    result = asyncio.run(chain.execute())
    assert result["ok"] is True
    assert result["provider"] == "B"


def test_audit_log_records():
    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings(audit_path=f"{tmp}/audit.log")
        al = AuditLog(settings)
        asyncio.run(al.record("test_event", {"key": "value"}))
        items = al.read(limit=10)
        assert len(items) >= 1
        assert items[-1]["type"] == "test_event"
