"""
Debate Adversarial Multi-Agente.

Para preguntas jurídicas delicadas, el reasoning lanza 3 perspectivas:
- Abogado de la parte actora (argumenta a favor)
- Abogado de la parte demandada (argumenta en contra)
- Magistrado (sintetiza y emite dictamen)

Esto reduce sesgo y fuerza citar contraargumentos.

NO es un chatbot - cada rol tiene prompt e instrucciones distintas.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from albra.config.settings import Settings
from albra.observability.logger import get_logger
from albra.providers.base import Provider


@dataclass
class DebateArgument:
    role: str
    argument: str
    citations: list[str] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class DebateResult:
    question: str
    arguments: list[DebateArgument] = field(default_factory=list)
    ruling: str = ""
    ruling_citations: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "arguments": [
                {
                    "role": a.role,
                    "argument": a.argument,
                    "citations": a.citations,
                    "confidence": a.confidence,
                }
                for a in self.arguments
            ],
            "ruling": self.ruling,
            "ruling_citations": self.ruling_citations,
        }


class AdversarialDebate:
    """Motor de debate adversarial."""

    ROLE_ACTOR = "abogado_parte_actora"
    ROLE_DEMANDADO = "abogado_parte_demandada"
    ROLE_MAGISTRADO = "magistrado"

    PROMPTS: dict[str, str] = {
        ROLE_ACTOR: (
            "Sos abogado de la parte actora. Argumentá a favor de la posición "
            "del usuario, buscando precedentes y fundamentos. CITA FUENTES. "
            "Si no podés fundamentar con fuente, DECLARÁ 'no encuentro fundamento'. "
            "NO inventes normas."
        ),
        ROLE_DEMANDADO: (
            "Sos abogado de la parte demandada. Argumentá en contra de la posición "
            "del usuario, identificando debilidades, excepciones, jurisprudencia "
            "opuesta. CITA FUENTES. Si no encontrás, declará 'no encuentro contraargumento'. "
            "NO inventes normas."
        ),
        ROLE_MAGISTRADO: (
            "Sos magistrado. Sintetizá los argumentos del actor y demandado. "
            "Emití un dictamen equilibrado. Si no hay fundamentos verificables "
            "de ambas partes, declará 'NO puede emitirse dictamen - falta evidencia'."
        ),
    }

    def __init__(self, settings: Settings, *, provider: Provider | None = None) -> None:
        self.settings = settings
        self.provider = provider
        self.log = get_logger("albra.debate")

    async def run_debate(self, question: str, *, rounds: int = 1) -> DebateResult:
        """Ejecuta el debate adversarial.

        rounds: cuántas rondas de ida y vuelta (por defecto 1).
        """
        result = DebateResult(question=question)

        for role in (self.ROLE_ACTOR, self.ROLE_DEMANDADO):
            arg = await self._argue(role, question)
            result.arguments.append(arg)

        # Magistrado sintetiza
        actor_arg = result.arguments[0].argument if result.arguments else ""
        demandado_arg = result.arguments[1].argument if len(result.arguments) > 1 else ""
        ruling = await self._rule(question, actor_arg, demandado_arg)
        result.ruling = ruling

        self.log.info(
            "debate.done",
            question=question[:50],
            n_args=len(result.arguments),
        )
        return result

    async def _argue(self, role: str, question: str) -> DebateArgument:
        prompt = f"{self.PROMPTS[role]}\n\nPregunta jurídica: {question}\n\nTu argumentación (máx 300 palabras):"
        if not self.provider:
            # Sin LLM - respuesta placeholder estructurada
            return DebateArgument(
                role=role,
                argument=(
                    f"[{role}] ALBRA no tiene LLM real conectado. "
                    "Cuando se cargue conocimiento jurídico y se configure un provider, "
                    "este rol argumentará con fundamentos citados. "
                    "Por ahora: el rol está arquitectónicamente presente, pero su voz está silenciada."
                ),
                citations=[],
                confidence=0.0,
            )
        try:
            resp = await self.provider.call(prompt)
            if not resp.ok:
                return DebateArgument(
                    role=role,
                    argument=f"[{role}] Error del provider: {resp.error}",
                    confidence=0.0,
                )
            return DebateArgument(
                role=role,
                argument=resp.text,
                citations=self._extract_citations(resp.text),
                confidence=0.7,
            )
        except Exception as e:  # noqa: BLE001
            return DebateArgument(
                role=role, argument=f"[{role}] Excepción: {e}", confidence=0.0
            )

    async def _rule(self, question: str, actor: str, demandado: str) -> str:
        prompt = (
            f"{self.PROMPTS[self.ROLE_MAGISTRADO]}\n\n"
            f"Pregunta: {question}\n\n"
            f"Argumento actor:\n{actor}\n\n"
            f"Argumento demandado:\n{demandado}\n\n"
            f"Dictamen del magistrado (máx 200 palabras):"
        )
        if not self.provider:
            return (
                "DICTAMEN: El magistrado no puede emitir pronunciamiento sin "
                "provider LLM configurado. Requerido para análisis adversarial real."
            )
        try:
            resp = await self.provider.call(prompt)
            return resp.text if resp.ok else f"Error: {resp.error}"
        except Exception as e:  # noqa: BLE001
            return f"Excepción: {e}"

    def _extract_citations(self, text: str) -> list[str]:
        """Extrae citas potenciales del texto (URLs o referencias)."""
        urls: list[str] = []
        words = text.split()
        for w in words:
            if w.startswith("http") or w.startswith("https"):
                urls.append(w.rstrip(".,;:"))
        return urls
