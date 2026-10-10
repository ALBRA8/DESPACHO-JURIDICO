"""Handler de audio - preparado para ASR (cuando se cargue)."""
from __future__ import annotations

from pathlib import Path


class AudioHandler:
    name = "audio"

    async def process(self, payload: dict) -> dict:
        path = payload.get("path")
        if not path:
            return {"ok": False, "error": "Falta path"}
        if not Path(path).exists():
            return {"ok": False, "error": f"Archivo no existe: {path}"}
        # Detectar formato por header
        with open(path, "rb") as f:
            header = f.read(12)
        kind = self._detect_kind(header)
        size = Path(path).stat().st_size
        return {
            "ok": True,
            "path": path,
            "kind": kind,
            "bytes": size,
            "transcription": None,
            "note": "ASR provider no conectado - transcripción pendiente",
        }

    def _detect_kind(self, header: bytes) -> str:
        if header.startswith(b"RIFF") and b"WAVE" in header[:12]:
            return "wav"
        if header.startswith(b"ID3") or header.startswith(b"\xff\xfb"):
            return "mp3"
        if header.startswith(b"OggS"):
            return "ogg"
        if header.startswith(b"ftyp"):
            return "m4a"
        return "unknown"

    async def startup(self) -> None: ...
    async def shutdown(self) -> None: ...
