"""Test del agente completo - integra todos los órganos."""
import asyncio

from albra.identity.agent import get_agent
from albra.identity.manifest import AGENT_MANIFEST


def test_agent_boots_all_organs():
    """Criterio: el agente nace con todos los órganos."""
    agent = get_agent()
    asyncio.run(agent.boot())
    # 30 órganos del ADN, pero algunos viven como instancias concretas
    expected = (
        "runtime", "reasoning", "tools", "capabilities",
        "mcp_server", "memory", "doctor", "events", "workflows",
        "providers", "security", "audit", "research", "evidence",
        "files", "comms", "resilience",
    )
    for organ in expected:
        assert organ in agent.organs, f"Falta órgano: {organ}"
    asyncio.run(agent.shutdown())


def test_agent_processes_greeting():
    agent = get_agent()
    asyncio.run(agent.boot())
    result = asyncio.run(agent.process("hola, qué más"))
    assert result["authorized"] is True
    assert "ALBRA" in result["reply"]
    asyncio.run(agent.shutdown())


def test_agent_legal_question_no_invention():
    """Criterio: NO inventa conocimiento jurídico."""
    agent = get_agent()
    asyncio.run(agent.boot())
    result = asyncio.run(agent.process("¿qué dice el código civil sobre contratos?"))
    # Debe decir que el conocimiento no está cargado
    assert "cargado" in result["reply"].lower() or "no inventa" in result["reply"].lower()
    asyncio.run(agent.shutdown())


def test_agent_uses_tool():
    agent = get_agent()
    asyncio.run(agent.boot())
    result = asyncio.run(agent.process("calcula 5*8"))
    assert result["tools_used"] or "40" in result["reply"] or "calcul" in result["reply"].lower()
    asyncio.run(agent.shutdown())


def test_agent_writes_memory():
    agent = get_agent()
    asyncio.run(agent.boot())
    asyncio.run(agent.process("hola"))
    stats = agent.organs["memory"].stats()  # MemoryInterface.stats() - nested dict
    # V1.6: stats retorna {"by_category": {...}, "total": int, "by_truth_level": {...}, ...}
    assert stats.get("total", 0) >= 1
    asyncio.run(agent.shutdown())


def test_agent_records_audit():
    agent = get_agent()
    asyncio.run(agent.boot())
    asyncio.run(agent.process("hola"))
    audit = agent.organs["audit"]
    items = audit.read(limit=10)
    assert len(items) >= 1
    asyncio.run(agent.shutdown())


def test_agent_doctor_can_diagnose():
    agent = get_agent()
    asyncio.run(agent.boot())
    doc = agent.organs["doctor"]
    report = asyncio.run(doc.diagnose(scope="all"))
    assert report.build_summary()["total"] > 0
    asyncio.run(agent.shutdown())


def test_agent_identity_not_constructor():
    """Criterio 35: NO modifica la fuente de verdad fuera del Constructor."""
    assert AGENT_MANIFEST.is_constructor is False
    assert AGENT_MANIFEST.can_modify_code is False
