"""
Consolidación Jerárquica de Memoria.

Memoria episódica (eventos, conversaciones) → memoria semántica
(conocimiento resumido, reutilizable).

El órgano Doctor puede ejecutar este proceso periódicamente.

Tipos:
- EPISODIC: hechos puntuales (este expediente, esta conversación)
- SEMANTIC: conocimiento destilado (doctrina, precedentes del despacho)
- PROCEDURAL: cómo se hacen las cosas (workflows, templates)

El proceso de consolidación:
1. Selecciona ítems episódicos antiguos
2. Los resume/agrupa
3. Crea ítems semánticos
4. Marca los episódicos como consolidados (active=0)
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any

from albra.observability.logger import get_logger
from albra.memory.store import MemoryDV
from albra.memory.categories import (
    MEM_CONVERSATIONAL,
    MEM_OPERATIONAL,
    MEM_KNOWLEDGE,
)


@dataclass
class ConsolidationStats:
    reviewed: int = 0
    consolidated: int = 0
    new_semantic: int = 0
    errors: int = 0


class HierarchicalConsolidator:
    """Consolida memoria episódica en memoria semántica."""

    def __init__(self, *, memory: MemoryDV) -> None:
        self.memory = memory
        self.log = get_logger("albra.memory.consolidator")

    async def consolidate_conversations(self, *, max_age_hours: int = 24, min_items: int = 5) -> ConsolidationStats:
        """Consolida conversaciones antiguas en items semánticos."""
        stats = ConsolidationStats()
        cutoff = time.time() - (max_age_hours * 3600)

        items = await self.memory.retrieve("", category=MEM_CONVERSATIONAL, top_k=200)
        old_items = [i for i in items if i.get("ts", 0) < cutoff]
        stats.reviewed = len(old_items)

        if len(old_items) < min_items:
            self.log.info("consolidator.skip", reason="not_enough_items", found=len(old_items))
            return stats

        # Agrupar por user (cada conversación de un user)
        by_user: dict[str, list[dict[str, Any]]] = {}
        for item in old_items:
            user = item.get("metadata", {}).get("user", "unknown")
            by_user.setdefault(user, []).append(item)

        for user, items in by_user.items():
            try:
                summary = self._summarize(items)
                if not summary:
                    continue
                # Crear item semántico
                await self.memory.write(
                    summary,
                    category=MEM_KNOWLEDGE,
                    metadata={
                        "type": "consolidated_conversation",
                        "user": user,
                        "source_items": [i["id"] for i in items],
                        "consolidated_at": time.time(),
                    },
                )
                stats.new_semantic += 1
                # Desactivar items episódicos
                for item in items:
                    await self.memory.deactivate(item["id"])
                    stats.consolidated += 1
            except Exception as e:  # noqa: BLE001
                self.log.warning("consolidator.item_error", error=str(e))
                stats.errors += 1

        self.log.info(
            "consolidator.done",
            reviewed=stats.reviewed,
            consolidated=stats.consolidated,
            new_semantic=stats.new_semantic,
        )
        return stats

    def _summarize(self, items: list[dict[str, Any]]) -> str:
        """Resume una lista de items en un texto semántico.

        Producción: usar LLM para resumir.
        Por ahora: concatena primeros 80 chars de cada uno.
        """
        snippets = [i.get("text", "")[:80] for i in items if i.get("text")]
        if not snippets:
            return ""
        return "Resumen consolidado: " + " | ".join(snippets[:5])

    async def run_full_cycle(self) -> ConsolidationStats:
        """Ejecuta consolidación completa (episódico → semántico)."""
        self.log.info("consolidator.full_cycle.start")
        return await self.consolidate_conversations(max_age_hours=1, min_items=3)
