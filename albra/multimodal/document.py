"""Handler de documentos - PDF, DOCX, etc."""
from __future__ import annotations

from pathlib import Path


class DocumentHandler:
    name = "document"

    async def process(self, payload: dict) -> dict:
        path = payload.get("path")
        if not path:
            return {"ok": False, "error": "Falta path"}
        p = Path(path)
        if not p.exists():
            return {"ok": False, "error": f"Archivo no existe: {path}"}
        ext = p.suffix.lower()
        text = ""
        kind = self._classify(ext)
        try:
            if kind == "pdf":
                text = await self._extract_pdf(p)
            elif kind == "docx":
                text = await self._extract_docx(p)
            elif kind == "txt":
                text = p.read_text(encoding="utf-8", errors="ignore")
            else:
                text = ""
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e), "path": path}

        return {
            "ok": True,
            "path": path,
            "kind": kind,
            "bytes": p.stat().st_size,
            "text": text,
            "text_len": len(text),
            "extractor_note": (
                "Extracción básica - para producción instalar pypdf/python-docx"
            ),
        }

    def _classify(self, ext: str) -> str:
        return {
            ".pdf": "pdf",
            ".docx": "docx",
            ".doc": "doc_legacy",
            ".txt": "txt",
            ".md": "markdown",
            ".xlsx": "xlsx",
            ".csv": "csv",
            ".json": "json",
            ".html": "html",
            ".xml": "xml",
        }.get(ext, "unknown")

    async def _extract_pdf(self, p: Path) -> str:
        try:
            import pypdf  # type: ignore[import]
        except ImportError:
            return "[pypdf no instalado - no se pudo extraer texto del PDF]"
        try:
            r = pypdf.PdfReader(str(p))
            return "\n".join(page.extract_text() or "" for page in r.pages)
        except Exception as e:  # noqa: BLE001
            return f"[Error extrayendo PDF: {e}]"

    async def _extract_docx(self, p: Path) -> str:
        try:
            import docx  # type: ignore[import]
        except ImportError:
            return "[python-docx no instalado - no se pudo extraer texto del DOCX]"
        try:
            d = docx.Document(str(p))
            return "\n".join(p.text for p in d.paragraphs)
        except Exception as e:  # noqa: BLE001
            return f"[Error extrayendo DOCX: {e}]"

    async def startup(self) -> None: ...
    async def shutdown(self) -> None: ...
