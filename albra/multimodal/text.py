"""Handler de texto - pasa el texto al reasoning engine."""
from __future__ import annotations


class TextHandler:
    name = "text"

    async def process(self, payload: dict) -> dict:
        text = payload.get("text", "")
        return {"ok": True, "text": text, "kind": "text"}

    async def startup(self) -> None: ...
    async def shutdown(self) -> None: ...
