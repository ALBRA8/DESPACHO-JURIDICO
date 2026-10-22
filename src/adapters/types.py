"""
AgentAdapter interface — Python implementation.

El agente es el cajero. Si el cajero se va, la caja registradora
(conocimiento, infraestructura, bridges, skills) se queda.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class StackType(Enum):
    NEXTJS = "nextjs"
    NODE = "node"
    PYTHON = "python"
    HYBRID = "hybrid"


class BridgeType(Enum):
    ZAI_SDK = "zai-sdk"
    PYTHON = "python"
    HTTP = "http"


@dataclass
class AgentCapability:
    operation: str
    description: str
    input_schema: Optional[Dict[str, Any]] = None
    output_schema: Optional[Dict[str, Any]] = None


@dataclass
class AdapterResult:
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class HealthStatus:
    healthy: bool
    latency: Optional[float] = None
    details: Optional[Dict[str, Any]] = None


@dataclass
class ProjectConfig:
    project_name: str
    stack: StackType = StackType.PYTHON
    environment: str = "development"
    bridges: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class BridgeConfig:
    type: BridgeType = BridgeType.ZAI_SDK
    enabled: bool = True
    config: Optional[Dict[str, Any]] = None


class AgentAdapter(ABC):
    """Interfaz que todo agente intercambiable debe implementar."""

    @property
    @abstractmethod
    def id(self) -> str: ...

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def version(self) -> str: ...

    @property
    @abstractmethod
    def capabilities(self) -> List[AgentCapability]: ...

    @abstractmethod
    async def initialize(self, context: "HarnessContext") -> None: ...

    @abstractmethod
    async def execute(self, operation: str, params: Dict[str, Any]) -> AdapterResult: ...

    @abstractmethod
    def can_handle(self, operation: str) -> bool: ...

    @abstractmethod
    async def health_check(self) -> HealthStatus: ...

    @abstractmethod
    async def shutdown(self) -> None: ...


# Forward reference
class HarnessContext:
    """Contexto que el arnés le pasa al agente al montarlo."""

    def __init__(
        self,
        bridges: Any,  # BridgeRegistry
        skills: Any,    # SkillRegistry
        knowledge: Any, # KnowledgeRegistry
        config: ProjectConfig,
    ) -> None:
        self.bridges = bridges
        self.skills = skills
        self.knowledge = knowledge
        self.config = config
