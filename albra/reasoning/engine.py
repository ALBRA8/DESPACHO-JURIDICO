"""
Motor de razonamiento ALBRA — V1.6.

P0.1: usa ProviderRouter REAL (con fallback + circuit breaker integration).

Pipeline:
INPUT → plan (reglas) → MEMORY CONTEXT → tool calls (vía guard externo)
→ respond() usa ProviderRouter → LLM Provider → STRUCTURED RESPONSE

Si el provider falla o no está → fallback a reglas (mock).
Toda invocación al provider se traza.
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
        # Wired en agent.boot()
        self._provider_router: Any = None
        self._provider_registry: Any = None

    def wire(self, *, provider_router: Any, provider_registry: Any) -> None:
        """Inyecta el router de providers - llamado por Agent.boot()."""
        self._provider_router = provider_router
        self._provider_registry = provider_registry
        self.log.info(
            "reasoning.wired",
            providers=list(provider_router.providers.keys()) if provider_router else [],
        )

    async def startup(self) -> None:
        self.log.info("reasoning.startup")

    async def shutdown(self) -> None:
        self.log.info("reasoning.shutdown")

    async def plan(self, message: str, *, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Plan basado en reglas + intent detection."""
        ctx = context or {}
        msg_lower = message.lower()

        data_layer = {
            "raw_message": message,
            "user": ctx.get("user", "anon"),
            "channel": ctx.get("channel", "text"),
        }
        sources_layer = [{"type": "user_input", "id": ctx.get("user", "anon")}]
        evidence_layer = [{"source": "user_input", "content": message, "ts": ctx.get("ts")}]
        intent = self._detect_intent(msg_lower)
        inferences_layer = [{"intent": intent["name"], "confidence": intent["confidence"]}]

        conclusions_layer: list[str] = []
        if intent["name"] == "greeting":
            conclusions_layer.append("Usuario saluda. Responder amablemente.")
        elif intent["name"] == "legal_question":
            conclusions_layer.append(
                "Pregunta jurídica. NO inventar doctrina. Decir que conocimiento no está cargado."
            )
        elif intent["name"] == "tool_request":
            conclusions_layer.append("Usuario requiere ejecutar una herramienta.")
        elif intent["name"] == "health_check":
            conclusions_layer.append("Usuario consulta estado del agente.")
        else:
            conclusions_layer.append("Intención no clara. Pedir aclaración.")

        steps: list[dict[str, Any]] = []
        if intent["name"] == "tool_request":
            tool = self._extract_tool(msg_lower)
            if tool:
                tool_input = self._extract_tool_input(tool, message)
                steps.append({"type": "tool_call", "tool": tool, "input": tool_input})

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
        classification: Any = None,
    ) -> dict[str, Any]:
        """Produce respuesta usando ProviderRouter si está disponible.

        Para preguntas LEGALES: siempre usa fallback local (no LLM).
        Para otras: intenta provider primero, fallback a reglas si falla.

        Returns:
            {"text": str, "provider": str, "intent": str, ...}
        """
        plan = plan or {}
        tool_results = tool_results or []
        intent = plan.get("intent", {"name": "unknown", "confidence": 0})

        # SAFETY: para legal_question SIEMPRE usar fallback local.
        # El sistema NO inventa conocimiento jurídico.
        if intent.get("name") == "legal_question":
            fallback_text = self._compose_response(message, intent, tool_results, plan)
            return {
                "text": fallback_text,
                "provider": "rules_fallback_legal",
                "intent": intent["name"],
                "confidence": intent["confidence"],
                "fallback": True,
            }

        # 1. Intentar vía provider (P0.1)
        provider_used = None
        provider_text: str | None = None
        if self._provider_router is not None:
            provider_used, provider_text = await self._try_provider(
                message, plan=plan, tool_results=tool_results, classification=classification
            )

        # 2. Si provider devolvió texto → usarlo
        if provider_text and provider_used:
            return {
                "text": provider_text,
                "provider": provider_used,
                "intent": intent["name"],
                "confidence": intent["confidence"],
            }

        # 3. Fallback a reglas locales
        fallback_text = self._compose_response(message, intent, tool_results, plan)
        return {
            "text": fallback_text,
            "provider": provider_used or "rules_fallback",
            "intent": intent["name"],
            "confidence": intent["confidence"],
            "fallback": True,
        }

    async def _try_provider(
        self,
        message: str,
        *,
        plan: dict[str, Any],
        tool_results: list[dict[str, Any]],
        classification: Any = None,
    ) -> tuple[str | None, str | None]:
        """Intenta invocar un provider vía router. Devuelve (provider_name, text).

        Si router no decide, provider falla, o provider no disponible → (None, None).
        """
        if self._provider_router is None or self._provider_registry is None:
            return None, None

        try:
            # Router decide basado en sensibilidad (classification)
            decision = self._provider_router.route(message, metadata={
                "classification": classification.classification.name if classification else None,
            })
            provider = self._provider_registry.get(decision.provider)
            if provider is None:
                self.log.warning(
                    "reasoning.provider_unavailable",
                    requested=decision.provider,
                    reason=decision.reason,
                )
                return None, None

            # Construir prompt
            prompt = self._build_prompt(message, plan, tool_results)
            self.log.info(
                "reasoning.provider_call",
                provider=decision.provider,
                sensitive=decision.sensitive,
                prompt_size=len(prompt),
            )
            resp = await provider.call(prompt)
            if not resp.ok:
                self.log.warning(
                    "reasoning.provider_failed",
                    provider=decision.provider, error=resp.error,
                )
                # Fallback a mock si hay uno
                if decision.provider != "mock":
                    mock = self._provider_registry.get("mock")
                    if mock:
                        resp = await mock.call(prompt)
                        if resp.ok:
                            return "mock", resp.text
                return None, None
            return decision.provider, resp.text
        except Exception as e:  # noqa: BLE001
            self.log.error("reasoning.provider_exception", error=str(e))
            return None, None

    def _build_prompt(
        self,
        message: str,
        plan: dict[str, Any],
        tool_results: list[dict[str, Any]],
    ) -> str:
        """Construye prompt para el LLM con contexto estructurado."""
        intent = plan.get("intent", {})
        tools_summary = "\n".join(
            f"- {r['tool']}: ok={r['result'].get('ok', False)}"
            for r in tool_results
        ) or "(ninguna)"
        return (
            f"Eres el Agente Base del Despacho Jurídico Digital ALBRA.\n"
            f"NO inventes conocimiento jurídico. Si se te pregunta por leyes, "
            f"dice que el conocimiento jurídico aún no está cargado.\n\n"
            f"Mensaje del usuario: {message}\n"
            f"Intención detectada: {intent.get('name', 'unknown')} "
            f"(confianza {intent.get('confidence', 0)})\n"
            f"Herramientas invocadas:\n{tools_summary}\n\n"
            f"Responde de forma concisa:"
        )

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
        if "calcul" in msg:
            return "calculator"
        if "busc" in msg:
            return "searcher"
        if "hora" in msg or "fecha" in msg:
            return "clock"
        return None

    def _extract_tool_input(self, tool: str, message: str) -> dict[str, Any]:
        if tool == "calculator":
            m = re.search(r"calcul(?:a|ar)\s+(.+)", message, re.IGNORECASE)
            if m:
                expr = m.group(1).strip().rstrip("?.").strip()
                return {"expression": expr}
            m = re.search(r"[\d\s\+\-\*\/\(\)\.\%\^]+", message)
            if m:
                return {"expression": m.group(0).strip()}
            return {"expression": ""}
        if tool == "clock":
            return {}
        if tool == "searcher":
            return {"query": message}
        return {}

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
            r = tr.get("result", {})
            if r.get("ok"):
                return f"Ejecuté la herramienta '{tr['tool']}'. Resultado: {r.get('value')}"
            return f"La herramienta '{tr['tool']}' falló: {r.get('error', 'error desconocido')}"
        if name == "tool_request":
            return (
                "Detecté intención de usar una herramienta, pero no pude identificar "
                "cuál. Especifique la herramienta y los parámetros."
            )
        return (
            "No tengo suficiente contexto para responder. ¿Podría reformular o "
            "especificar la acción deseada?"
        )
