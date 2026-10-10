"""
Base de canal ALBRA.

Canal = punto de entrada/salida de mensajes entre humano y agente.
Adapters concretos: WhatsApp, Telegram, texto, voz.

El cerebro del agente NO depende del canal. Los adapters solo traducen
formatos y mantienen identidad de conversación.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChannelMessage:
    channel: str
    user: str
    text: str
    ts: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)
    attachments: list[dict[str, Any]] = field(default_factory=list)


class ChannelAdapter(ABC):
    name: str = "abstract"

    @abstractmethod
    async def receive(self) -> list[ChannelMessage]:
        """Recibe mensajes pendientes del canal."""

    @abstractmethod
    async def send(self, to: str, text: str, *, reply_to: str | None = None) -> dict[str, Any]:
        """Envía un mensaje por el canal."""

    async def startup(self) -> None: ...

    async def shutdown(self) -> None: ...
