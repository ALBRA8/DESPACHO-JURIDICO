"""Loader de conocimiento jurídico - VACÍO por diseño."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from albra.config.settings import Settings
from albra.observability.logger import get_logger


class KnowledgeLoader:
    """Carga conocimiento jurídico desde archivos estructurados.

    Formato esperado (YAML/JSON):
    ---
    kind: law
    jurisdiction: CO
    source: https://www...
    source_type: official
    effective_from: 1991-07-04
    effective_to: null
    title: Constitución Política de Colombia
    articles:
      - id: art-1
        text: ...
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.log = get_logger("albra.knowledge.loader")
        self._knowledge_path = Path(settings.knowledge_path)
        self._knowledge_path.mkdir(parents=True, exist_ok=True)
        self._items: list[dict[str, Any]] = []

    async def startup(self) -> None:
        self.log.info(
            "knowledge.startup",
            jurisdiction=self.settings.knowledge_jurisdiction,
            note="Knowledge layer vacío por diseño. El conocimiento jurídico se cargará después.",
        )

    async def shutdown(self) -> None:
        self.log.info("knowledge.shutdown")

    async def load_from_path(self, path: str) -> dict[str, Any]:
        """Carga items de conocimiento desde un directorio o archivo."""
        p = Path(path)
        if not p.exists():
            return {"ok": False, "error": f"Path no existe: {path}"}

        items_loaded = 0
        files_scanned = 0
        for f in self._iter_files(p, suffixes={".yaml", ".yml", ".json"}):
            files_scanned += 1
            try:
                items = self._parse_file(f)
                self._items.extend(items)
                items_loaded += len(items)
            except Exception as e:  # noqa: BLE001
                self.log.warning("knowledge.parse_fail", file=str(f), error=str(e))
        self.log.info("knowledge.loaded", files=files_scanned, items=items_loaded)
        return {"ok": True, "items_loaded": items_loaded, "files_scanned": files_scanned}

    def _iter_files(self, p: Path, *, suffixes: set[str]):
        if p.is_file() and p.suffix in suffixes:
            yield p
            return
        for f in p.rglob("*"):
            if f.suffix in suffixes:
                yield f

    def _parse_file(self, f: Path) -> list[dict[str, Any]]:
        text = f.read_text(encoding="utf-8", errors="ignore")
        if f.suffix == ".json":
            import json
            data = json.loads(text)
        else:
            import yaml  # type: ignore[import]
            data = yaml.safe_load(text)
        if isinstance(data, list):
            return [self._normalize_item(d) for d in data]
        if isinstance(data, dict):
            return [self._normalize_item(data)]
        return []

    def _normalize_item(self, d: dict[str, Any]) -> dict[str, Any]:
        return {
            "kind": d.get("kind", "unknown"),
            "jurisdiction": d.get("jurisdiction", self.settings.knowledge_jurisdiction),
            "source": d.get("source", ""),
            "source_type": d.get("source_type", "unknown"),
            "title": d.get("title", ""),
            "effective_from": d.get("effective_from"),
            "effective_to": d.get("effective_to"),
            "text": d.get("text", ""),
            "articles": d.get("articles", []),
            "metadata": d.get("metadata", {}),
            "loaded_from": str(Path(__file__).resolve()),
        }

    def list_items(self) -> list[dict[str, Any]]:
        return self._items

    def stats(self) -> dict[str, Any]:
        return {
            "items": len(self._items),
            "knowledge_path": str(self._knowledge_path),
            "is_loaded": len(self._items) > 0,
            "note": "Capa de conocimiento jurídico vacía por diseño. Cargar normas Colombia en fase posterior.",
        }
