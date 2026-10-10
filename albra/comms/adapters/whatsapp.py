"""
WhatsApp Cloud API Adapter (Meta).

NO simula la integración. Si no hay token configurado, falla explícitamente.
Documentación: https://developers.facebook.com/docs/whatsapp/cloud-api
"""
from __future__ import annotations

import time
from typing import Any

from albra.comms.base import ChannelAdapter, ChannelMessage
from albra.config.settings import Settings
from albra.observability.logger import get_logger


class WhatsAppAdapter(ChannelAdapter):
    name = "whatsapp"

    BASE_URL = "https://graph.facebook.com/v18.0"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.log = get_logger("albra.comms.whatsapp")
        self._token = settings.whatsapp_token
        self._phone_id = settings.whatsapp_phone_id
        self._incoming: list[ChannelMessage] = []

    async def receive(self) -> list[ChannelMessage]:
        # WhatsApp envía webhooks - necesitamos un endpoint HTTP.
        # Aquí solo devolvemos lo que llegó vía webhook_push().
        msgs = list(self._incoming)
        self._incoming.clear()
        return msgs

    def webhook_push(self, payload: dict[str, Any]) -> None:
        """Procesa un webhook de WhatsApp Cloud API."""
        try:
            entry = payload["entry"][0]
            changes = entry["changes"][0]
            value = changes["value"]
            messages = value.get("messages", [])
            contact = value.get("contacts", [{}])[0]
            user = contact.get("wa_id", "unknown")
            name = contact.get("profile", {}).get("name", "")
            for m in messages:
                text = m.get("text", {}).get("body", "")
                self._incoming.append(
                    ChannelMessage(
                        channel="whatsapp",
                        user=user,
                        text=text,
                        ts=time.time(),
                        raw=m,
                        metadata_extra={"name": name},  # type: ignore[call-arg]
                    )
                )
        except (KeyError, IndexError) as e:
            self.log.warning("whatsapp.webhook.parse_fail", error=str(e))

    async def send(self, to: str, text: str, *, reply_to: str | None = None) -> dict[str, Any]:
        if not self._token or not self._phone_id:
            return {
                "ok": False,
                "error": "WHATSAPP_TOKEN o PHONE_ID no configurados",
            }
        try:
            import httpx  # type: ignore[import]
        except ImportError:
            return {"ok": False, "error": "httpx no instalado"}

        url = f"{self.BASE_URL}/{self._phone_id}/messages"
        headers = {"Authorization": f"Bearer {self._token}"}
        body = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": text},
        }
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(url, headers=headers, json=body)
                r.raise_for_status()
                return {"ok": True, "response": r.json()}
        except Exception as e:  # noqa: BLE001
            self.log.error("whatsapp.send.error", error=str(e))
            return {"ok": False, "error": str(e)}

    async def startup(self) -> None:
        if not self._token:
            self.log.warning("whatsapp.startup.no_token")
