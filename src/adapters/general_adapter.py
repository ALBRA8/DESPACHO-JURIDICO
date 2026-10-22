"""
GeneralAdapter — el agente intercambiable.

Este es el "cajero". Se monta sobre el arnés.
Si se va, el conocimiento, bridges y skills se quedan.
"""
from __future__ import annotations

from typing import Any, Dict, List

from src.adapters.types import (
    AdapterResult,
    AgentAdapter,
    AgentCapability,
    HarnessContext,
    HealthStatus,
)


class GeneralAdapter(AgentAdapter):
    """AGENTE-GENERAL — agente de conocimiento en blanco.

    No tiene conocimiento del dominio. Todo el conocimiento
    está en el arnés (KnowledgeRegistry, SkillRegistry).
    """

    @property
    def id(self) -> str:
        return "agente-general"

    @property
    def name(self) -> str:
        return "AGENTE-GENERAL"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def capabilities(self) -> List[AgentCapability]:
        return [
            AgentCapability(operation="chat", description="Conversación con IA via bridges"),
            AgentCapability(operation="generate", description="Generación de contenido"),
            AgentCapability(operation="analyze", description="Análisis de datos/texto"),
            AgentCapability(operation="validate", description="Validación contra reglas del dominio"),
            AgentCapability(operation="execute-skill", description="Ejecutar skill del arnés"),
            AgentCapability(operation="query-knowledge", description="Consultar conocimiento del dominio"),
            AgentCapability(operation="legal-query", description="Consulta jurídica via LegalKnowledgeEngine"),
        ]

    def __init__(self) -> None:
        self._context: HarnessContext | None = None

    async def initialize(self, context: HarnessContext) -> None:
        self._context = context
        bridge_list = context.bridges.list()
        print(f"[GeneralAdapter] Montado. Bridges: {[b['type'] for b in bridge_list]}")
        print(f"[GeneralAdapter] Skills: {len(context.skills.list())}")
        print(f"[GeneralAdapter] Knowledge: {len(context.knowledge.list())}")

    async def execute(self, operation: str, params: Dict[str, Any]) -> AdapterResult:
        if not self._context:
            return AdapterResult(success=False, error="Adapter not initialized")

        try:
            if operation in ("chat", "generate", "analyze"):
                result = await self._context.bridges.execute(operation, params)
                return AdapterResult(
                    success=result.success,
                    data=result.data,
                    error=result.error,
                    metadata={"source": result.source},
                )

            elif operation == "validate":
                knowledge_id = params.get("knowledgeId", "")
                knowledge_module = self._context.knowledge.get(knowledge_id)
                if not knowledge_module:
                    return AdapterResult(
                        success=False,
                        error=f"Knowledge module not found: {knowledge_id}",
                    )
                bridge_result = await self._context.bridges.execute("chat", {
                    "messages": [
                        {"role": "system", "content": f"Usa estas reglas: {knowledge_module.get_content()}"},
                        {"role": "user", "content": f"Valida: {params.get('data', '')}"},
                    ],
                })
                return AdapterResult(
                    success=bridge_result.success,
                    data=bridge_result.data,
                    metadata={"source": bridge_result.source},
                )

            elif operation == "execute-skill":
                skill_result = await self._context.skills.execute(
                    params.get("skillId", ""),
                    params.get("skillOperation", ""),
                    self._build_skill_context(params.get("params", {})),
                )
                return AdapterResult(
                    success=skill_result.success,
                    data=skill_result.data,
                    error=skill_result.error,
                )

            elif operation == "query-knowledge":
                module = self._context.knowledge.get(params.get("moduleId", ""))
                if not module:
                    return AdapterResult(
                        success=False,
                        error=f"Knowledge module not found: {params.get('moduleId', '')}",
                    )
                return AdapterResult(success=True, data=module.get_content())

            elif operation == "legal-query":
                # Delegate to ALBRA's LegalKnowledgeEngine via the runtime
                from albra.identity.agent import get_agent
                agent = get_agent()
                if not agent._booted:
                    await agent.boot()
                result = await agent.process(
                    params.get("query", ""),
                    user=params.get("user", "harness"),
                    user_role=params.get("role", "admin"),
                )
                return AdapterResult(
                    success=result.get("authorized", False),
                    data=result,
                    metadata={"routed_to": result.get("routed_to", "reasoning")},
                )

            else:
                return AdapterResult(success=False, error=f"Unknown operation: {operation}")

        except Exception as e:
            return AdapterResult(success=False, error=str(e))

    def can_handle(self, operation: str) -> bool:
        return any(c.operation == operation for c in self.capabilities)

    async def health_check(self) -> HealthStatus:
        if not self._context:
            return HealthStatus(healthy=False, details={"error": "Not initialized"})
        bridge_list = self._context.bridges.list()
        knowledge_health = self._context.knowledge.health_check()
        return HealthStatus(
            healthy=len(bridge_list) > 0,
            details={
                "bridges": len(bridge_list),
                "knowledge_total": knowledge_health["total"],
                "knowledge_valid": knowledge_health["valid"],
            },
        )

    async def shutdown(self) -> None:
        self._context = None
        print("[GeneralAdapter] Desconectado")

    def _build_skill_context(self, params: Dict[str, Any]):
        from src.harness.types import SkillContext
        return SkillContext(
            bridges=self._context.bridges,
            knowledge=self._context.knowledge,
            agent=self,
            params=params,
        )
