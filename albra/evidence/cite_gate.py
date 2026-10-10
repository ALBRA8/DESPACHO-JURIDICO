"""
CITE-OR-REFUSE GATE.

El despacho jurídico NUNCA emite una afirmación legal sin cita verificable.
Si no puede citar fuente oficial, el gate devuelve refuse=True.

Pipeline:
1. Reasoning propone una conclusión
2. Gate busca evidencia con source_type='official'
3. Si no hay → refuse
4. Si hay → devuelve con la cita

Esto es lo que diferencia a ALBRA de un chatbot alucinador.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from albra.config.settings import Settings
from albra.observability.logger import get_logger


@dataclass
class CitationGateResult:
    refused: bool
    reason: str
    citations: list[dict[str, Any]] = field(default_factory=list)
    safe_text: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "refused": self.refused,
            "reason": self.reason,
            "citations": self.citations,
            "safe_text": self.safe_text,
        }


class CiteOrRefuseGate:
    """Gate que bloquea afirmaciones legales sin cita verificable."""

    # Marcas de afirmación legal que requieren cita
    LEGAL_ASSERTION_PATTERNS: tuple[str, ...] = (
        "el artículo",
        "la ley",
        "el código",
        "el estatuto",
        "la constitución",
        "la jurisprudencia",
        "el reglamento",
        "la norma",
        "según la corte",
        "de acuerdo con",
    )

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.log = get_logger("albra.cite_gate")

    def looks_like_legal_assertion(self, text: str) -> bool:
        text_l = text.lower()
        return any(p in text_l for p in self.LEGAL_ASSERTION_PATTERNS)

    async def evaluate(
        self,
        text: str,
        *,
        evidence_chain: Any = None,
        jurisdiction: str | None = None,
    ) -> CitationGateResult:
        """Evalúa si un texto puede ser emitido como afirmación legal."""
        if not self.looks_like_legal_assertion(text):
            # No es afirmación legal - pasa sin cita
            return CitationGateResult(
                refused=False,
                reason="No legal assertion detected",
                safe_text=text,
            )

        # Buscar evidencia oficial
        citations: list[dict[str, Any]] = []
        if evidence_chain:
            try:
                all_evidence = evidence_chain.list(limit=200)
                for ev in all_evidence:
                    source_type = ev.get("metadata", {}).get("type", "unknown")
                    if source_type == "official":
                        citations.append(
                            {
                                "evidence_id": ev["id"],
                                "source": ev.get("source", ""),
                                "kind": ev.get("kind", ""),
                                "snippet": (ev.get("content", ""))[:120],
                            }
                        )
                        if len(citations) >= 3:
                            break
            except Exception as e:  # noqa: BLE001
                self.log.warning("cite_gate.evidence_error", error=str(e))

        if not citations:
            return CitationGateResult(
                refused=True,
                reason=(
                    "ALBRA no puede emitir esta afirmación legal sin cita verificable. "
                    "El conocimiento jurídico aún no está cargado o no se encontró "
                    "fuente oficial asociada."
                ),
                safe_text=(
                    "Esta afirmación requiere citar fuente oficial verificable. "
                    "Hasta que el conocimiento jurídico sea cargado y trazable, "
                    "ALBRA no emite doctrina."
                ),
            )

        # Texto con citas anotadas
        safe = text + "\n\nFuentes:\n"
        for i, c in enumerate(citations, start=1):
            safe += f"{i}. {c['source']} (evidence: {c['evidence_id']})\n"
        return CitationGateResult(
            refused=False,
            reason="Citations found",
            citations=citations,
            safe_text=safe,
        )

    async def startup(self) -> None:
        self.log.info("cite_gate.startup")

    async def shutdown(self) -> None:
        self.log.info("cite_gate.shutdown")
