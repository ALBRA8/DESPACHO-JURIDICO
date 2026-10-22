"""Tests del ARNÉS ALBRA — migración proyecto → arnés."""
import asyncio

import pytest

from src.adapters.types import (
    AdapterResult,
    AgentCapability,
    HealthStatus,
    ProjectConfig,
    StackType,
)
from src.bootstrap import bootstrap
from src.bridges.types import BridgeRegistry, IBridge, PythonBridge, ZaiSdkBridge
from src.harness.knowledge_registry import KnowledgeRegistry, register_builtin_knowledge
from src.harness.types import SkillRegistry


@pytest.fixture
def harness():
    """Arnés inicializado."""
    return bootstrap()


class TestBootstrap:
    def test_bootstrap_returns_context(self, harness):
        assert harness is not None
        assert harness.bridges is not None
        assert harness.skills is not None
        assert harness.knowledge is not None
        assert harness.config is not None

    def test_project_name(self, harness):
        assert harness.config.project_name == "DESPACHO JURIDICO ALBRA"

    def test_stack_python(self, harness):
        assert harness.config.stack == StackType.PYTHON


class TestBridges:
    def test_two_bridges_registered(self, harness):
        bridges = harness.bridges.list()
        assert len(bridges) == 2
        types = [b["type"] for b in bridges]
        assert "zai-sdk" in types
        assert "python" in types

    def test_zai_sdk_is_priority(self, harness):
        # ZAI SDK should be first in priority
        assert "zai-sdk" in harness.bridges._priority
        assert harness.bridges._priority[0] == "zai-sdk"

    def test_python_bridge_available(self, harness):
        bridge = harness.bridges._bridges.get("python")
        assert bridge is not None
        result = asyncio.run(bridge.is_available())
        assert result is True

    def test_bridge_fallback(self, harness):
        """Si ZAI SDK no está disponible, Python bridge toma el relevo."""
        result = asyncio.run(harness.bridges.execute("nonexistent_op", {}))
        # Should try both bridges and fail gracefully
        assert result.success is False
        assert result.source in ("none", "zai-sdk", "python")


class TestKnowledge:
    def test_seven_modules(self, harness):
        modules = harness.knowledge.list()
        assert len(modules) == 7

    def test_all_valid(self, harness):
        health = harness.knowledge.health_check()
        assert health["total"] == 7
        assert health["valid"] == 7
        assert health["invalid"] == []

    def test_legal_schemas(self, harness):
        mod = harness.knowledge.get("legal-schemas")
        assert mod is not None
        content = mod.get_content()
        assert "document_types" in content
        assert "constitucion" in content["document_types"]

    def test_corpus_pilot(self, harness):
        mod = harness.knowledge.get("corpus-pilot")
        assert mod is not None
        content = mod.get_content()
        assert content["total_documents"] == 3
        assert content["total_articles"] == 12

    def test_firewall_policies(self, harness):
        mod = harness.knowledge.get("firewall-policies")
        assert mod is not None
        content = mod.get_content()
        assert "send_external_message" in content

    def test_specialists(self, harness):
        mod = harness.knowledge.get("specialists")
        assert mod is not None
        content = mod.get_content()
        assert "civil" in content
        assert "penal" in content

    def test_get_by_category(self, harness):
        domain = harness.knowledge.get_by_category("domain-specific")
        assert len(domain) >= 5

    def test_get_nonexistent(self, harness):
        assert harness.knowledge.get("nonexistent") is None


class TestGeneralAdapter:
    def test_adapter_id(self):
        from src.adapters.general_adapter import GeneralAdapter
        adapter = GeneralAdapter()
        assert adapter.id == "agente-general"
        assert adapter.name == "AGENTE-GENERAL"
        assert adapter.version == "1.0.0"

    def test_capabilities(self):
        from src.adapters.general_adapter import GeneralAdapter
        adapter = GeneralAdapter()
        caps = adapter.capabilities
        operations = [c.operation for c in caps]
        assert "chat" in operations
        assert "legal-query" in operations
        assert "query-knowledge" in operations

    def test_can_handle(self):
        from src.adapters.general_adapter import GeneralAdapter
        adapter = GeneralAdapter()
        assert adapter.can_handle("chat") is True
        assert adapter.can_handle("legal-query") is True
        assert adapter.can_handle("nonexistent") is False

    def test_query_knowledge(self, harness):
        from src.adapters.general_adapter import GeneralAdapter
        adapter = GeneralAdapter()
        asyncio.run(adapter.initialize(harness))
        result = asyncio.run(adapter.execute("query-knowledge", {"moduleId": "legal-schemas"}))
        assert result.success is True
        assert "document_types" in result.data

    def test_query_nonexistent_knowledge(self, harness):
        from src.adapters.general_adapter import GeneralAdapter
        adapter = GeneralAdapter()
        asyncio.run(adapter.initialize(harness))
        result = asyncio.run(adapter.execute("query-knowledge", {"moduleId": "nonexistent"}))
        assert result.success is False
        assert "not found" in result.error.lower()

    def test_unknown_operation(self, harness):
        from src.adapters.general_adapter import GeneralAdapter
        adapter = GeneralAdapter()
        asyncio.run(adapter.initialize(harness))
        result = asyncio.run(adapter.execute("nonexistent", {}))
        assert result.success is False
        assert "Unknown operation" in result.error

    def test_health_check(self, harness):
        from src.adapters.general_adapter import GeneralAdapter
        adapter = GeneralAdapter()
        asyncio.run(adapter.initialize(harness))
        health = asyncio.run(adapter.health_check())
        assert health.healthy is True
        assert health.details["bridges"] == 2
        assert health.details["knowledge_total"] == 7

    def test_health_check_not_initialized(self):
        from src.adapters.general_adapter import GeneralAdapter
        adapter = GeneralAdapter()
        health = asyncio.run(adapter.health_check())
        assert health.healthy is False

    def test_shutdown(self, harness):
        from src.adapters.general_adapter import GeneralAdapter
        adapter = GeneralAdapter()
        asyncio.run(adapter.initialize(harness))
        asyncio.run(adapter.shutdown())
        health = asyncio.run(adapter.health_check())
        assert health.healthy is False


class TestHarnessAPI:
    def test_list_bridges(self, harness):
        bridges = harness.bridges.list()
        assert len(bridges) == 2

    def test_list_knowledge(self, harness):
        modules = harness.knowledge.list()
        assert len(modules) == 7

    def test_knowledge_health(self, harness):
        health = harness.knowledge.health_check()
        assert health["valid"] == 7
        assert health["invalid"] == []


class TestLIPO:
    """Tests que verifican la separación agente vs arnés."""

    def test_agent_has_no_domain_knowledge(self):
        """El agente NO debe tener conocimiento del dominio embebido."""
        import inspect

        from src.adapters.general_adapter import GeneralAdapter
        src = inspect.getsource(GeneralAdapter)
        # No debe mencionar términos específicos del dominio jurídico
        assert "constitucion" not in src.lower()
        assert "ley_100" not in src.lower()
        assert "sentencia" not in src.lower()
        assert "jurisprudencia" not in src.lower()

    def test_knowledge_has_domain_content(self, harness):
        """El arnés SÍ debe tener conocimiento del dominio."""
        # Legal schemas
        schemas = harness.knowledge.get("legal-schemas")
        assert schemas is not None
        content = schemas.get_content()
        assert "constitucion" in content["document_types"]

        # Corpus pilot
        corpus = harness.knowledge.get("corpus-pilot")
        assert corpus is not None
        corpus_content = corpus.get_content()
        assert corpus_content["total_documents"] == 3

    def test_agent_delegates_to_harness(self, harness):
        """El agente delega al arnés para operaciones de conocimiento."""
        from src.adapters.general_adapter import GeneralAdapter
        adapter = GeneralAdapter()
        asyncio.run(adapter.initialize(harness))

        # El agente no sabe qué hay en legal-schemas
        # Pero puede consultarlo via query-knowledge
        result = asyncio.run(adapter.execute("query-knowledge", {"moduleId": "legal-schemas"}))
        assert result.success is True
        assert "document_types" in result.data
