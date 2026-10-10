"""
Motor de razonamiento ALBRA.

Plan: descompone el input en pasos.
Respond: produce una respuesta basada en plan + tool_results.

POR AHORA usa un razonamiento basado en reglas + templates
(sin LLM externo). El adaptador de LLM (providers) se conecta aquí.
"""
from __future__ import annotations

import re
from typing import Any

from albra.config.settings import Settings
from albra.observability.logger import get_logger
from albra.reasoning.layers import (
    LAYER_ACTIONS,
    LAYER_CONCLUSIONS,
    LAYER_DATA,
    LAYER_EVIDENCE,
    LAYER_INFERENCES,
    LAYER_SOURCES,
)


class ReasoningEngine:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.log = get_logger("albra.reasoning")

    async def startup(self) -> None:
        self.log.info("reasoning.startup")

    async def shutdown(self) -> None:
        self.log.info("reasoning.shutdown")

    async def plan(self, message: str, *, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Plan básico: detecta intención y propone pasos.

        NO inventa conocimiento jurídico. Si el input parece legal,
        marca la intención pero NO responde con doctrina inventada.
        """
        ctx = context or {}
        msg_lower = message.lower()

        # Capa DATA
        data_layer = {
            "raw_message": message,
            "user": ctx.get("user", "anon"),
            "channel": ctx.get("channel", "text"),
        }

        # Capa SOURCES
        sources_layer = [
            {"type": "user_input", "id": ctx.get("user", "anon")},
        ]

        # Capa EVIDENCE
        evidence_layer = [
            {"source": "user_input", "content": message, "ts": ctx.get("ts")},
        ]

        # Capa INFERENCES - detectar intención
        intent = self._detect_intent(msg_lower)
        inferences_layer = [{"intent": intent, "confidence": intent["confidence"]}]

        # Capa CONCLUSIONS
        conclusions_layer = []
        if intent["name"] == "greeting":
            conclusions_layer.append("Usuario saluda. Responder amablemente sin emitir doctrina.")
        elif intent["name"] == "legal_question":
            conclusions_layer.append(
                "Pregunta jurídica detectada. NO inventar doctrina. "
                "Responder que el conocimiento jurídico aún no está cargado."
            )
        elif intent["name"] == "tool_request":
            conclusions_layer.append("Usuario requiere ejecutar una herramienta.")
        elif intent["name"] == "health_check":
            conclusions_layer.append("Usuario consulta estado del agente.")
        else:
            conclusions_layer.append("Intención no clara. Pedir aclaración.")

        # Capa ACTIONS
        steps: list[dict[str, Any]] = []
        if intent["name"] == "tool_request":
            tool = self._extract_tool(msg_lower)
            if tool:
                steps.append({"type": "tool_call", "tool": tool, "input": {}})

        return {
            "summary": "; ".join(conclusions_layer),
            "intent": intent,
            "steps": steps,
            "layers": {
                LAYER_DATA: data_layer,
                LAYER_SOURCES: sources_layer,
                LAYER_EVIDENCE: evidence_layer,
                LAYER_INFERENCES: inferences_layer,
                LAYER_CONCLUSIONS: conclusions_layer,
                LAYER_ACTIONS: steps,
            },
        }

    async def respond(
        self,
        message: str,
        *,
        plan: dict[str, Any] | None = None,
        tool_results: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Produce la respuesta final basada en plan + resultados de tools."""
        plan = plan or {}
        tool_results = tool_results or []
        intent = plan.get("intent", {"name": "unknown", "confidence": 0})

        text = self._compose_response(message, intent, tool_results, plan)
        return {
            "text": text,
            "intent": intent["name"],
            "confidence": intent["confidence"],
            "layers": plan.get("layers", {}),
        }

    # --- Helpers ---

    def _detect_intent(self, msg: str) -> dict[str, Any]:
        greetings = ("hola", "buenas", "hello", "hi", "saludos", "qué más", "que mas", "epa")
        legal_kw = (
            "ley", "derecho", "jurídico", "juridico", "abogado", "demanda", "contrato",
            "constitución", "constitucion", "código", "codigo", "norma", "artículo",
            "articulo", "sentencia", "régimen", "regimen", "jurisprudencia",
        )
        health_kw = ("estado", "status", "doctor", "salud", "diagnóstico", "diagnostico")
        tool_kw = ("calcul", "ejecuta", "ejecutar", "buscar", "envía", "envia", "genera", "hora", "fecha")

        if any(g in msg for g in greetings):
            return {"name": "greeting", "confidence": 0.85}
        if any(k in msg for k in legal_kw):
            return {"name": "legal_question", "confidence": 0.75}
        if any(k in msg for k in health_kw):
            return {"name": "health_check", "confidence": 0.7}
        if any(k in msg for k in tool_kw):
            return {"name": "tool_request", "confidence": 0.65}
        return {"name": "unknown", "confidence": 0.3}

    def _extract_tool(self, msg: str) -> str | None:
        # Mapa simple: si menciona "calcula" → calculator, "buscar" → searcher, etc.
        if "calcul" in msg:
            return "calculator"
        if "busc" in msg:
            return "searcher"
        if "hora" in msg or "fecha" in msg:
            return "clock"
        return None

    def _compose_response(
        self,
        message: str,
        intent: dict[str, Any],
        tool_results: list[dict[str, Any]],
        plan: dict[str, Any],
    ) -> str:
        name = intent.get("name", "unknown")

        if name == "greeting":
            return (
                "Saludos. Soy el Agente Base del Despacho Jurídico Digital ALBRA. "
                "Mi arquitectura está operativa, pero el conocimiento jurídico se "
                "incorporará progresivamente. ¿En qué puedo ayudarle dentro de "
                "mis capacidades actuales?"
            )
        if name == "legal_question":
            return (
                "Detecto una consulta jurídica. Sin embargo, debo informar que "
                "el conocimiento jurídico aún no ha sido cargado en el sistema. "
                "ALBRA no inventa doctrina ni normas. La primera jurisdicción "
                "objetivo es Colombia. Cuando se alimente la capa de conocimiento, "
                "podré responder con trazabilidad a fuentes oficiales."
            )
        if name == "health_check":
            return (
                "Estado del organismo: arquitectura operativa. Órganos activos "
                "incluyen runtime, memoria, reasoning, tools, MCP, doctor, eventos "
                "y observabilidad. Ejecuta 'albra doctor' para diagnóstico completo."
            )
        if name == "tool_request" and tool_results:
            tr = tool_results[-1]
            return f"Ejecuté la herramienta '{tr['tool']}'. Resultado: {tr['result']}"
        if name == "tool_request":
            return (
                "Detecté intención de usar una herramienta, pero no pude identificar "
                "cuál. Especifique la herramienta y los parámetros."
            )
        return (
            "No tengo suficiente contexto para responder. ¿Podría reformular o "
            "especificar la acción deseada?"
        )
