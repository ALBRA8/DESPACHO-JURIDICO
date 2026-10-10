"""
Router de canales ALBRA.

- Registra adapters
- Recibe mensajes de cualquier canal
- Los pasa al agente con metadatos
- Devuelve respuestas al canal correcto

Mantiene: identidad de conversación, usuario, contexto, historial.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from albra.config.settings import Settings
from albra.observability.logger import get_logger
from albra.comms.base import ChannelAdapter, ChannelMessage


class CommRouter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.log = get_logger("albra.comms")
        self._adapters: dict[str, ChannelAdapter] = {}
        self._sessions: dict[str, dict[str, Any]] = defaultdict(dict)
        self._agent_handler: Any = None  # callback async (message) -> reply
        self._running = False

    def register_adapter(self, name: str, adapter: ChannelAdapter) -> None:
        if name in self._adapters:
            raise ValueError(f"Adapter '{name}' ya registrado")
        self._adapters[name] = adapter
        self.log.info("comms.adapter.registered", name=name)

    def set_agent_handler(self, handler: Any) -> None:
        """handler: async fn(message: ChannelMessage) -> str"""
        self._agent_handler = handler

    async def startup(self) -> None:
        # Auto-registrar adapters según settings
        from albra.comms.adapters.text import TextAdapter
        self.register_adapter("text", TextAdapter())

        if self.settings.whatsapp_enabled:
            from albra.comms.adapters.whatsapp import WhatsAppAdapter
            self.register_adapter("whatsapp", WhatsAppAdapter(self.settings))

        if self.settings.telegram_enabled:
            from albra.comms.adapters.telegram import TelegramAdapter
            self.register_adapter("telegram", TelegramAdapter(self.settings))

        for adapter in self._adapters.values():
            await adapter.startup()
        self.log.info("comms.startup", adapters=list(self._adapters.keys()))

    async def shutdown(self) -> None:
        self._running = False
        for adapter in self._adapters.values():
            await adapter.shutdown()
        self.log.info("comms.shutdown")

    async def route_in(self, message: ChannelMessage) -> dict[str, Any]:
        """Recibe un mensaje entrante, lo pasa al handler del agente."""
        session_id = f"{message.channel}:{message.user}"
        session = self._sessions[session_id]
        session["last_seen"] = message.ts
        session["messages"] = session.get("messages", 0) + 1

        self.log.info(
            "comms.route_in",
            channel=message.channel,
            user=message.user,
            session=session_id,
        )

        if not self._agent_handler:
            return {"reply": "", "error": "no agent handler wired"}

        try:
            reply_text = await self._agent_handler(message)
        except Exception as e:  # noqa: BLE001
            self.log.error("comms.handler.error", error=str(e))
            reply_text = "Error interno procesando mensaje."

        # Enviar respuesta por el mismo canal
        adapter = self._adapters.get(message.channel)
        if adapter:
            await adapter.send(message.user, reply_text, reply_to=message.user)

        return {"reply": reply_text, "channel": message.channel, "session": session_id}

    async def route_out(self, channel: str, to: str, text: str) -> dict[str, Any]:
        """Envía un mensaje saliente por un canal específico."""
        adapter = self._adapters.get(channel)
        if not adapter:
            return {"ok": False, "error": f"Canal '{channel}' no registrado"}
        return await adapter.send(to, text)

    async def loop(self, *, interval: float = 1.0) -> None:
        """Loop de polling para adapters que necesitan receive()."""
        self._running = True
        self.log.info("comms.loop.start")
        while self._running:
            for name, adapter in list(self._adapters.items()):
                try:
                    messages = await adapter.receive()
                    for msg in messages:
                        await self.route_in(msg)
                except Exception as e:  # noqa: BLE001
                    self.log.warning("comms.adapter.error", adapter=name, error=str(e))
            await asyncio.sleep(interval)

    def list_adapters(self) -> list[str]:
        return list(self._adapters.keys())

    def session_info(self, channel: str, user: str) -> dict[str, Any]:
        return dict(self._sessions.get(f"{channel}:{user}", {}))
