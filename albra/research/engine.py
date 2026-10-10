"""
Motor de investigación ALBRA.

Independiente del componente "Chismoso" (que tiene sus propias funciones).

Pipeline:
- buscar información
- consultar fuentes
- identificar fuentes relevantes
- comparar fuentes
- detectar cambios
- verificar información
- evaluar confiabilidad
- registrar procedencia
- mantener evidencia

Para temas jurídicos: priorizar fuentes oficiales y autorizadas.
NO presentar como hecho aquello que no pudo verificarse.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from albra.config.settings import Settings
from albra.observability.logger import get_logger
from albra.evidence.chain import EvidenceChain


@dataclass
class Source:
    url: str
    title: str
    type: str  # official | unofficial | unknown
    fetched_at: float = field(default_factory=time.time)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class Finding:
    query: str
    source: Source
    snippet: str
    confidence: float  # 0.0 - 1.0
    verified: bool = False


class ResearchEngine:
    """Motor de investigación con trazabilidad.

    NOTA: la implementación real de búsqueda web requiere integración
    con un servicio externo (search API). La arquitectura está preparada;
    cuando se configure, el método `search()` hará llamadas reales.
    """

    # Fuentes oficiales prioritarias para Colombia (jurídicas)
    PRIORITY_SOURCES_CO: tuple[str, ...] = (
        "https://www.funcionpublica.gov.co",
        "https://www.ramajudicial.gov.co",
        "https://www.minjusticia.gov.co",
        "https://www.supersociedades.gov.co",
        "https://www.corteconstitucional.gov.co",
        "https://www.alcaldiabogota.gov.co",
    )

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.log = get_logger("albra.research")
        self._search_backend: Any = None  # wired later (search API client)
        self._evidence: EvidenceChain | None = None

    def wire(self, *, evidence_chain: EvidenceChain) -> None:
        self._evidence = evidence_chain

    async def startup(self) -> None:
        self.log.info("research.startup", jurisdiction=self.settings.knowledge_jurisdiction)

    async def shutdown(self) -> None:
        self.log.info("research.shutdown")

    async def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        jurisdiction: str | None = None,
    ) -> dict[str, Any]:
        """Búsqueda con resultado NO INVENTADO.

        Si no hay backend de búsqueda configurado, devuelve empty + note.
        """
        self.log.info("research.search", query=query, top_k=top_k, jurisdiction=jurisdiction)
        findings: list[Finding] = []

        if self._search_backend is None:
            return {
                "ok": False,
                "error": "no_search_backend",
                "note": (
                    "Backend de búsqueda externa no configurado. "
                    "ALBRA no inventa resultados. Configurar un Search provider MCP."
                ),
                "findings": [],
                "evidence_ids": [],
            }

        try:
            raw_results = await self._search_backend(query, top_k=top_k)
            for r in raw_results:
                url = r.get("url", "")
                source = Source(
                    url=url,
                    title=r.get("title", ""),
                    type=self._classify_source(url, jurisdiction),
                    raw=r,
                )
                findings.append(
                    Finding(
                        query=query,
                        source=source,
                        snippet=r.get("snippet", ""),
                        confidence=r.get("confidence", 0.5),
                        verified=False,
                    )
                )
        except Exception as e:  # noqa: BLE001
            self.log.error("research.search.error", error=str(e))
            return {"ok": False, "error": str(e), "findings": []}

        # Registrar evidencia
        evidence_ids: list[str] = []
        if self._evidence:
            for f in findings:
                eid = await self._evidence.add(
                    kind="research_finding",
                    content=f.snippet,
                    source=f.source.url,
                    metadata={"title": f.source.title, "type": f.source.type},
                )
                evidence_ids.append(eid)

        return {
            "ok": True,
            "findings": [self._finding_to_dict(f) for f in findings],
            "evidence_ids": evidence_ids,
        }

    def _classify_source(self, url: str, jurisdiction: str | None) -> str:
        if not url:
            return "unknown"
        if jurisdiction == "CO" or jurisdiction is None:
            for off in self.PRIORITY_SOURCES_CO:
                if off in url:
                    return "official"
        if ".gov." in url or "gob." in url:
            return "official"
        return "unofficial"

    def _finding_to_dict(self, f: Finding) -> dict[str, Any]:
        return {
            "query": f.query,
            "source_url": f.source.url,
            "source_title": f.source.title,
            "source_type": f.source.type,
            "snippet": f.snippet,
            "confidence": f.confidence,
            "verified": f.verified,
        }
