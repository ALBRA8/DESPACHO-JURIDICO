"""Handler de imágenes - arquitectura preparada, implementación con VLM cuando se cargue."""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Any


class ImageHandler:
    """Procesamiento de imágenes.

    Capacidades preparadas:
    - lectura (bytes / base64)
    - clasificación (cuando se conecte un VLM provider)
    - extracción de texto OCR (cuando se conecte)
    - comparación de imágenes
    - transformaciones
    """

    name = "image"

    async def process(self, payload: dict) -> dict:
        path = payload.get("path")
        b64 = payload.get("base64")
        if not path and not b64:
            return {"ok": False, "error": "Falta path o base64"}
        try:
            if path:
                data = Path(path).read_bytes()
            else:
                data = base64.b64decode(b64)
            # Header detection
            kind = self._detect_kind(data[:8])
            return {
                "ok": True,
                "bytes": len(data),
                "kind": kind,
                "note": "VLM no conectado - solo metadatos disponibles",
            }
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}

    def _detect_kind(self, header: bytes) -> str:
        if header.startswith(b"\xff\xd8"):
            return "jpeg"
        if header.startswith(b"\x89PNG"):
            return "png"
        if header.startswith(b"GIF8"):
            return "gif"
        if header[:2] in (b"BM",):
            return "bmp"
        if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
            return "webp"
        return "unknown"

    async def startup(self) -> None: ...
    async def shutdown(self) -> None: ...
