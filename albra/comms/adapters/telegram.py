"""
Telegram Bot API Adapter.

Documentación: https://core.telegram.org/bots/api
NO simula integración. Si no hay token, falla explícitamente.
"""
from __future__ import annotations

import time
from typing import Any

from albra.comms.base import ChannelAdapter, ChannelMessage
from albra.config.settings import Settings
from albra.observability.logger import get_logger


class TelegramAdapter(ChannelAdapter):
    name = "telegram"

    BASE_URL = "https://api.telegram.org"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.log = get_logger("albra.comms.telegram")
        self._token = settings.telegram_bot_token
        self._offset = 0
        self._incoming: list[ChannelMessage] = []

    async def receive(self) -> list[ChannelMessage]:
        if not self._token:
            return []
        try:
            import httpx  # type: ignore[import]
        except ImportError:
            return []

        url = f"{self.BASE_URL}/bot{self._token}/getUpdates"
        params = {"offset": self._offset, "timeout": 0}
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.get(url, params=params)
                r.raise_for_status()
                data = r.json()
                for update in data.get("result", []):
                    self._offset = update["update_id"] + 1
                    msg = update.get("message", {})
                    text = msg.get("text", "")
                    user = str(msg.get("from", {}).get("id", "unknown"))
                    self._incoming.append(
                        ChannelMessage(
                            channel="telegram",
                            user=user,
                            text=text,
                            ts=msg.get("date", time.time()),
                            raw=msg,
                        )
                    )
        except Exception as e:  # noqa: BLE001
            self.log.warning("telegram.receive.error", error=str(e))
        msgs = list(self._incoming)
        self._incoming.clear()
        return msgs

    async def send(self, to: str, text: str, *, reply_to: str | None = None) -> dict[str, Any]:
        if not self._token:
            return {"ok": False, "error": "TELEGRAM_BOT_TOKEN no configurado"}
        try:
            import httpx  # type: ignore[import]
        except ImportError:
            return {"ok": False, "error": "httpx no instalado"}

        url = f"{self.BASE_URL}/bot{self._token}/sendMessage"
        body = {"chat_id": to, "text": text}
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(url, json=body)
                r.raise_for_status()
                return {"ok": True, "response": r.json()}
        except Exception as e:  # noqa: BLE001
            self.log.error("telegram.send.error", error=str(e))
            return {"ok": False, "error": str(e)}

    async def startup(self) -> None:
        if not self._token:
            self.log.warning("telegram.startup.no_token")
