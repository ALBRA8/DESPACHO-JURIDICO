"""Adapter de voz - placeholder arquitectónico."""
from __future__ import annotations

from albra.comms.base import ChannelAdapter, ChannelMessage


class VoiceAdapter(ChannelAdapter):
    """Para futura integración con ASR/TTS.

    NO implementa ahora - solo deja la arquitectura preparada.
    """

    name = "voice"

    async def receive(self) -> list[ChannelMessage]:
        return []

    async def send(self, to: str, text: str, *, reply_to: str | None = None) -> dict:
        return {"ok": False, "error": "Voice adapter no implementado todavía"}
