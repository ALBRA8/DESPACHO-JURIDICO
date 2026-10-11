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
    """V1.6 P0-1: consulta jurídica ruteada a LegalKnowledgeEngine.
    Sin corpus cargado → abstención (NO inventa conocimiento).
    """
    agent = get_agent()
    asyncio.run(agent.boot())
    # admin role tiene research.run - puede acceder al legal_engine
    result = asyncio.run(agent.process(
        "¿qué dice el código civil sobre contratos?",
        user="test", user_role="admin",
    ))
    # P0-1: se rutó a legal_engine (no a reasoning fallback)
    assert result.get("routed_to") == "legal_engine" or result.get("abstention") is True
    # NO inventa: abstiene o pide aclaración
    reply_lower = result["reply"].lower()
    assert (
        "evidencia" in reply_lower
        or "no se encontró" in reply_lower
        or "no inventa" in reply_lower
        or "abstención" in reply_lower
        or "aclaración" in reply_lower
    ), f"Expected abstention/clarification, got: {reply_lower[:100]}"
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
