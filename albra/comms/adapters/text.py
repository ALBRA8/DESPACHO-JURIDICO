"""Adapter de texto - canal stdin/stdout."""
from __future__ import annotations

import sys
from typing import Any

from albra.comms.base import ChannelAdapter, ChannelMessage


class TextAdapter(ChannelAdapter):
    name = "text"

    def __init__(self) -> None:
        self._queue: list[ChannelMessage] = []

    async def receive(self) -> list[ChannelMessage]:
        msgs = list(self._queue)
        self._queue.clear()
        return msgs

    async def send(self, to: str, text: str, *, reply_to: str | None = None) -> dict[str, Any]:
        print(f"[ALBRA → {to}] {text}", file=sys.stdout, flush=True)
        return {"ok": True, "channel": "text", "to": to}

    def push_from_stdin(self, user: str, text: str) -> None:
        """Método para testing/integración manual."""
        import time
        self._queue.append(
            ChannelMessage(channel="text", user=user, text=text, ts=time.time())
        )
