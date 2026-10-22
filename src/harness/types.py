"""
Skill Registry — skills del arnés.

Cada skill es un plugin que define operaciones del dominio.
El agente intercambiable ejecuta skills via el adapter.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


class SkillCategory(str):
    VALIDATION = "validation"
    GENERATION = "generation"
    ANALYSIS = "analysis"
    ASSEMBLY = "assembly"
    REVIEW = "review"
    ORCHESTRATION = "orchestration"
    DOMAIN_SPECIFIC = "domain-specific"


@dataclass
class SkillParamDef:
    type: str  # string | number | boolean | object | array
    required: bool = True
    description: str = ""


@dataclass
class SkillOperation:
    id: str
    name: str
    description: str
    params: Optional[Dict[str, SkillParamDef]] = None


@dataclass
class SkillResult:
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None


class SkillContext:
    """Contexto que se le pasa a un skill cuando se ejecuta."""

    def __init__(
        self,
        bridges: Any,     # BridgeRegistry
        knowledge: Any,   # KnowledgeRegistry
        agent: Any,       # AgentAdapter
        params: Dict[str, Any],
    ) -> None:
        self.bridges = bridges
        self.knowledge = knowledge
        self.agent = agent
        self.params = params


class ISkillPlugin(ABC):
    """Interfaz que todo skill plugin debe implementar."""

    @property
    @abstractmethod
    def id(self) -> str: ...

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def category(self) -> str: ...

    @property
    @abstractmethod
    def operations(self) -> List[SkillOperation]: ...

    @abstractmethod
    async def execute(self, operation: str, context: SkillContext) -> SkillResult: ...


    async def startup(self) -> None: ...
    async def shutdown(self) -> None: ...


class SkillRegistry:
    """Registry de skills del arnés."""

    def __init__(self) -> None:
        self._skills: Dict[str, ISkillPlugin] = {}

    def register(self, skill: ISkillPlugin) -> None:
        self._skills[skill.id] = skill

    def get(self, skill_id: str) -> Optional[ISkillPlugin]:
        return self._skills.get(skill_id)

    def list(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": s.id,
                "name": s.name,
                "category": s.category,
                "operations": [o.id for o in s.operations],
            }
            for s in self._skills.values()
        ]

    def find_by_category(self, category: str) -> List[ISkillPlugin]:
        return [s for s in self._skills.values() if s.category == category]

    async def execute(
        self,
        skill_id: str,
        operation: str,
        context: SkillContext,
    ) -> SkillResult:
        skill = self._skills.get(skill_id)
        if not skill:
            return SkillResult(success=False, error=f"Skill not found: {skill_id}")
        if not any(o.id == operation for o in skill.operations):
            return SkillResult(
                success=False,
                error=f"Operation {operation} not found in skill {skill_id}",
            )
        return await skill.execute(operation, context)

    async def startup(self) -> None:
        for skill in self._skills.values():
            await skill.startup()

    async def shutdown(self) -> None:
        for skill in self._skills.values():
            await skill.shutdown()
