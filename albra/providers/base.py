"""Base de Provider ALBRA."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProviderResponse:
    ok: bool
    text: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class Provider(ABC):
    """Provider abstracto - cualquier servicio externo."""

    name: str = "abstract"
    kind: str = "general"

    @abstractmethod
    async def call(self, prompt: str, **kwargs: Any) -> ProviderResponse: ...

    async def startup(self) -> None: ...

    async def shutdown(self) -> None: ...
