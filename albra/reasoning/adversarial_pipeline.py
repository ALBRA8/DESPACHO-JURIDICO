"""
ADVERSARIAL PIPELINE RED→BLUE — el propio sistema ataca las posiciones
antes de presentarlas.

Inspiración (clean-room, NO copy): GLAW (RED→BLUE pipeline antes de file),
Lavern (debate protocol), albra/reasoning/debate.py (already exists,
AdversarialDebate class — this V2.2-C is its evolution with structured roles).

Pipeline:
1. RED phase: toma el draft (markdown text) + matter context. Genera 3-5
   contra-argumentos estructurados. Cada uno con:
   - id (UUID)
   - role="red"
   - target_clause (párrafo del draft al que ataca, por índice)
   - argument (string, contra-argumento)
   - evidence (lista de normas/citas que apoyan)
   - severity (low/medium/high)
2. BLUE phase: por cada RED argument, BLUE genera defense:
   - id (UUID)
   - role="blue"
   - responds_to (red argument id)
   - argument (defense string)
   - evidence (lista)
   - confidence (0.0-1.0)
3. MAGISTRADO phase: por cada par RED+BLUE, emite ruling:
   - red_argument_id, blue_response_id
   - ruling: SUSTAINED | OVERRULED | SPLIT (parcial)
   - reason (string)
4. Pipeline devuelve RedBluePipelineResult con:
   - red_arguments (list)
   - blue_responses (list)
   - rulings (list)
   - overall_strength_score (0.0-1.0, basado en % SUSTAINED de BLUE)
   - recommendation: PROCEED_TO_FILE | RETRADE | ABANDON

V2.2 (rule-based, no LLM):
- RED: split draft por párrafos, detecta debilidades (falta de cita,
  afirmación sin evidencia, no considera contra-argumento).
- BLUE: lookup al corpus V1.1 (CitationAuditor + LocalRAG) para citar
  norma aplicable; si no encuentra, baja confianza a 0.4.
- MAGISTRADO: reglas determinísticas sobre (confidence, evidence).

V2.3+: inyectar provider real (anthropic/openai/mock) para generar
argumentos reales con LLM. La interfaz pública (run + dataclasses)
permanece estable.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any

from albra.knowledge.citation_audit import CitationAuditor
from albra.knowledge.rag_local import LocalRAG, default_rag
from albra.llm.router import LLMRouter
from albra.observability.logger import get_logger


# =========================================================================
# Dataclasses (patrón albra/knowledge/citation_audit.py)
# =========================================================================
@dataclass
class RedArgument:
    """Contra-argumento generado por la fase RED."""

    id: str
    target_clause_index: int  # párrafo del draft al que ataca
    argument: str
    role: str = "red"
    evidence: list[str] = field(default_factory=list)  # normas/citas que apoyan
    severity: str = "low"  # low | medium | high

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "role": self.role,
            "target_clause_index": self.target_clause_index,
            "argument": self.argument,
            "evidence": list(self.evidence),
            "severity": self.severity,
        }


@dataclass
class BlueResponse:
    """Defensa generada por la fase BLUE a un RedArgument."""

    id: str
    responds_to: str  # red argument id
    argument: str
    role: str = "blue"
    evidence: list[str] = field(default_factory=list)
    confidence: float = 0.0  # 0.0-1.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "role": self.role,
            "responds_to": self.responds_to,
            "argument": self.argument,
            "evidence": list(self.evidence),
            "confidence": self.confidence,
        }


@dataclass
class MagistradoRuling:
    """Fallo del MAGISTRADO sobre un par RED+BLUE."""

    red_argument_id: str
    blue_response_id: str
    ruling: str  # SUSTAINED | OVERRULED | SPLIT
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "red_argument_id": self.red_argument_id,
            "blue_response_id": self.blue_response_id,
            "ruling": self.ruling,
            "reason": self.reason,
        }


@dataclass
class RedBluePipelineResult:
    """Resultado del pipeline RED→BLUE→MAGISTRADO."""

    red_arguments: list[RedArgument]
    blue_responses: list[BlueResponse]
    rulings: list[MagistradoRuling]
    overall_strength_score: float
    recommendation: str  # PROCEED_TO_FILE | RETRADE | ABANDON
    draft_summary: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "red_arguments": [a.as_dict() for a in self.red_arguments],
            "blue_responses": [b.as_dict() for b in self.blue_responses],
            "rulings": [r.as_dict() for r in self.rulings],
            "overall_strength_score": self.overall_strength_score,
            "recommendation": self.recommendation,
            "draft_summary": self.draft_summary,
        }


# =========================================================================
# AdversarialPipeline
# =========================================================================
class AdversarialPipeline:
    """Pipeline adversarial RED→BLUE antes de file.

    V2.2 (rule-based, no LLM): usa CitationAuditor + LocalRAG del corpus
    V1.1 para generar respuestas estructuradas. Para V2.3+, inyectar
    llm_provider real; la interfaz pública (run + dataclasses) no cambia.
    """

    MAX_RED_ARGUMENTS = 5
    MIN_PARAGRAPH_LENGTH = 50

    # Términos que indican claim jurídico sustantivo
    LEGAL_CLAIM_TERMS: tuple[str, ...] = (
        "demanda", "tutela", "acción", "pretensión", "pretende", "solicita",
    )

    # Términos que indican afirmación/fundamentación
    ASSERTION_TERMS: tuple[str, ...] = (
        "afirma", "establece", "garantiza", "derecho", "obligación",
        "fundamenta", "ampara",
    )

    RECOMMEND_PROCEED = "PROCEED_TO_FILE"
    RECOMMEND_RETRADE = "RETRADE"
    RECOMMEND_ABANDON = "ABANDON"

    def __init__(self, llm_router: LLMRouter | None = None) -> None:
        """
        llm_router: opcional (V2.3+). Si None, usa heurísticas rule-based
        (V2.2 default). Si se inyecta, RED/BLUE/MAGISTRADO usan LLM para
        generar argumentos; si LLM falla o JSON parse falla, fallback
        a rule-based (V2.2).

        Uso:
            pipeline = AdversarialPipeline()  # rule-based
            pipeline = AdversarialPipeline(llm_router=get_default_router())
            pipeline = AdversarialPipeline(llm_router=LLMRouter("anthropic"))
        """
        self._llm_router = llm_router
        self.log = get_logger("albra.reasoning.adversarial_pipeline")
        # Corpus V1.1 lookup helpers
        self._auditor = CitationAuditor()
        self._rag: LocalRAG = default_rag()

    # ===== Pipeline orquestador =====

    def run(
        self,
        draft_markdown: str,
        matter_context: dict | None = None,
    ) -> RedBluePipelineResult:
        """Pipeline completo: RED → BLUE → MAGISTRADO.

        matter_context: dict con client, area, parties, pretensions (opcional).
        En V2.2 rule-based, matter_context se acepta pero no se usa para
        generar argumentos (sólo logging). En V2.3+ con LLM sí se usará.
        """
        if not draft_markdown or not draft_markdown.strip():
            self.log.info("adversarial_pipeline.empty_draft")
            return RedBluePipelineResult(
                red_arguments=[],
                blue_responses=[],
                rulings=[],
                overall_strength_score=1.0,
                recommendation=self.RECOMMEND_PROCEED,
                draft_summary="(empty draft)",
            )

        red_args = self._red_phase(draft_markdown, matter_context)
        blue_resps = self._blue_phase(draft_markdown, red_args)
        rulings = self._magistrado_phase(red_args, blue_resps)
        score, recommendation = self._recommend(rulings)
        summary = self._summarize(draft_markdown)

        self.log.info(
            "adversarial_pipeline.complete",
            red=len(red_args),
            blue=len(blue_resps),
            rulings=len(rulings),
            score=score,
            recommendation=recommendation,
        )
        return RedBluePipelineResult(
            red_arguments=red_args,
            blue_responses=blue_resps,
            rulings=rulings,
            overall_strength_score=score,
            recommendation=recommendation,
            draft_summary=summary,
        )

    # ===== Phase 1: RED =====

    def _red_phase(
        self,
        draft_markdown: str,
        matter_context: dict | None,
    ) -> list[RedArgument]:
        """Genera 3-5 contra-argumentos estructurados.

        V2.3+ (con LLM router inyectado):
        - Construye prompt estructurado (draft + matter_context) pidiendo
          JSON [{target_clause, argument, evidence, severity}].
        - Si LLM responde y JSON parsea → RedArgument objects desde el JSON.
        - Si LLM falla o JSON no parsea → fallback a rule-based (V2.2).

        V2.2 (rule-based, no LLM):
        - Split draft por párrafos (split por '\\n\\n')
        - Por cada párrafo sustantivo (>= 50 chars), generar 1 RED argument
          con patrones:
          - 'El párrafo {i} no cita norma específica'
          - 'El párrafo {i} hace afirmación sin evidencia'
          - 'El párrafo {i} no considera contra-argumento de la contraparte'
        - Severity: 'high' si el párrafo tiene palabras como 'demanda', 'tutela'
          y no cita norma; 'medium' si tiene claim pero sin evidencia;
          'low' si solo falta contexto.
        - Evidence: lista vacía o referencias genéricas a corpus.
        """
        # V2.3+ LLM path: si router inyectado, intentar generar vía LLM
        if self._llm_router is not None:
            llm_args = self._red_phase_llm(draft_markdown, matter_context)
            if llm_args is not None:
                return llm_args
            self.log.info("adversarial_pipeline.red_fallback_to_rules")

        paragraphs = self._split_paragraphs(draft_markdown)
        args: list[RedArgument] = []
        # matter_context accepted for V2.3+ LLM use; rule-based ignores it
        _ = matter_context

        for idx, p in enumerate(paragraphs):
            if len(p) < self.MIN_PARAGRAPH_LENGTH:
                continue
            if len(args) >= self.MAX_RED_ARGUMENTS:
                break

            lowered = p.lower()
            has_legal_claim = any(t in lowered for t in self.LEGAL_CLAIM_TERMS)
            has_assertion = any(t in lowered for t in self.ASSERTION_TERMS)
            citations = self._auditor.extract_citations(p)
            verified, _unverified, _rejected = self._auditor.validate_against_corpus(
                citations
            )

            if not citations:
                if has_legal_claim:
                    severity = "high"
                    arg_text = (
                        f"El párrafo {idx} no cita norma específica pese a contener "
                        "claim jurídico sustantivo ('demanda'/'tutela')."
                    )
                elif has_assertion:
                    severity = "medium"
                    arg_text = (
                        f"El párrafo {idx} hace afirmación sin evidencia: "
                        "no respalda su claim con cita normativa."
                    )
                else:
                    severity = "low"
                    arg_text = (
                        f"El párrafo {idx} no cita norma específica — "
                        "falta de anclaje jurídico."
                    )
                evidence: list[str] = []
            elif not verified:
                # Tiene citas pero ninguna está en corpus V1.1
                severity = "medium"
                arg_text = (
                    f"El párrafo {idx} hace afirmación sin evidencia verificable "
                    "(citas presentes pero no en corpus V1.1)."
                )
                evidence = []
            else:
                # Citas verificadas presentes — otra debilidad: falta contra-arg
                severity = "low"
                arg_text = (
                    f"El párrafo {idx} no considera contra-argumento "
                    "de la contraparte."
                )
                evidence = []

            args.append(
                RedArgument(
                    id=str(uuid.uuid4()),
                    target_clause_index=idx,
                    argument=arg_text,
                    role="red",
                    evidence=evidence,
                    severity=severity,
                )
            )
        return args

    def _red_phase_llm(
        self,
        draft_markdown: str,
        matter_context: dict | None,
    ) -> list[RedArgument] | None:
        """LLM path para RED phase. Devuelve lista o None (fallback).

        Construye prompt estructurado, llama al router, parsea JSON list.
        Si la lista parsea y no está vacía, crea RedArgument objects.
        Si LLM lanza excepción o JSON no parsea, devuelve None
        (caller cae a rule-based V2.2).
        """
        try:
            prompt = self._build_red_prompt(draft_markdown, matter_context)
            response = self._llm_router.generate(prompt)  # type: ignore[union-attr]
            items = self._parse_json_list(response.text)
            args: list[RedArgument] = []
            for item in items[: self.MAX_RED_ARGUMENTS]:
                if not isinstance(item, dict):
                    continue
                tc = int(item.get("target_clause", 0) or 0)
                arg_text = str(item.get("argument", "")).strip()
                if not arg_text:
                    continue
                ev_raw = item.get("evidence", [])
                if isinstance(ev_raw, str):
                    ev_raw = [ev_raw]
                elif not isinstance(ev_raw, list):
                    ev_raw = []
                sev = str(item.get("severity", "medium")).lower()
                if sev not in ("low", "medium", "high"):
                    sev = "medium"
                args.append(
                    RedArgument(
                        id=str(uuid.uuid4()),
                        target_clause_index=tc,
                        argument=arg_text,
                        role="red",
                        evidence=[str(e) for e in ev_raw],
                        severity=sev,
                    )
                )
            if not args:
                return None
            return args
        except Exception as e:  # noqa: BLE001 — fallback control
            self.log.warning(
                "adversarial_pipeline.red_llm_failed",
                error=str(e)[:120],
            )
            return None

    def _build_red_prompt(
        self,
        draft_markdown: str,
        matter_context: dict | None,
    ) -> str:
        """Construye prompt para RED phase (3 contra-argumentos en JSON)."""
        ctx_str = (
            json.dumps(matter_context, ensure_ascii=False, default=str)
            if matter_context
            else "{}"
        )
        return (
            "Genera 3 contra-argumentos estructurados para el siguiente draft "
            "jurídico. Cada contra-argumento debe identificar: target_clause "
            "(índice del párrafo), argument (texto), evidence (lista de normas), "
            "severity (low/medium/high).\n\n"
            f"Draft: {draft_markdown}\n"
            f"Matter context: {ctx_str}\n\n"
            "Formato JSON: "
            '[{"target_clause": int, "argument": str, "evidence": [str], '
            '"severity": str}]'
        )

    # ===== Phase 2: BLUE =====

    def _blue_phase(
        self,
        draft_markdown: str,
        red_arguments: list[RedArgument],
    ) -> list[BlueResponse]:
        """Por cada RED, genera BLUE defense.

        V2.3+ (con LLM router inyectado):
        - Por cada RED argument, prompt pidiendo JSON
          {argument, evidence, confidence}.
        - Si LLM responde y JSON parsea → BlueResponse desde el JSON.
        - Si LLM falla o JSON no parsea → fallback a rule-based (V2.2).

        V2.2 (rule-based):
        - Si RED dice 'no cita norma': BLUE responde 'La norma aplicable es
          Constitución art. X' (lookup al corpus V1.1)
        - Si RED dice 'no considera contra-argumento': BLUE responde 'Se
          considera en párrafo Y' o 'Pendiente fortalecer'
        - confidence: 0.8 si BLUE puede citar norma del corpus, 0.4 si no.
        """
        # V2.3+ LLM path
        if self._llm_router is not None:
            llm_resps = self._blue_phase_llm(draft_markdown, red_arguments)
            if llm_resps is not None:
                return llm_resps
            self.log.info("adversarial_pipeline.blue_fallback_to_rules")

        paragraphs = self._split_paragraphs(draft_markdown)
        responses: list[BlueResponse] = []

        for red in red_arguments:
            idx = red.target_clause_index
            paragraph = paragraphs[idx] if idx < len(paragraphs) else ""
            arg_lower = red.argument.lower()

            if "no cita norma" in arg_lower:
                cite_str, evidence, confidence = self._lookup_norm(paragraph)
                if cite_str:
                    blue_arg = f"La norma aplicable es {cite_str}."
                else:
                    blue_arg = (
                        "Pendiente fortalecer — no se identificó norma aplicable "
                        "en el corpus V1.1."
                    )
            elif "sin evidencia" in arg_lower:
                blue_arg = (
                    "Pendiente fortalecer — se debe aportar evidencia "
                    "empírica o documental para el claim del párrafo."
                )
                evidence = []
                confidence = 0.4
            elif "no considera" in arg_lower:
                blue_arg = (
                    "Pendiente fortalecer — se debe incorporar y rebatir "
                    "el contra-argumento esperado de la contraparte."
                )
                evidence = []
                confidence = 0.4
            else:
                blue_arg = (
                    "Se fortalecerá la fundamentación del párrafo antes del file."
                )
                evidence = []
                confidence = 0.4

            responses.append(
                BlueResponse(
                    id=str(uuid.uuid4()),
                    responds_to=red.id,
                    argument=blue_arg,
                    role="blue",
                    evidence=evidence,
                    confidence=confidence,
                )
            )
        return responses

    def _blue_phase_llm(
        self,
        draft_markdown: str,
        red_arguments: list[RedArgument],
    ) -> list[BlueResponse] | None:
        """LLM path para BLUE phase. Devuelve lista o None (fallback)."""
        try:
            responses: list[BlueResponse] = []
            for red in red_arguments:
                prompt = self._build_blue_prompt(draft_markdown, red)
                response = self._llm_router.generate(prompt)  # type: ignore[union-attr]
                parsed = self._parse_json_object(response.text)
                arg_text = str(parsed.get("argument", "")).strip()
                if not arg_text:
                    arg_text = "Defensa generada por LLM."
                ev_raw = parsed.get("evidence", [])
                if isinstance(ev_raw, str):
                    ev_raw = [ev_raw]
                elif not isinstance(ev_raw, list):
                    ev_raw = []
                try:
                    confidence = float(parsed.get("confidence", 0.5))
                except (TypeError, ValueError):
                    confidence = 0.5
                # Clamp 0..1
                confidence = max(0.0, min(1.0, confidence))
                responses.append(
                    BlueResponse(
                        id=str(uuid.uuid4()),
                        responds_to=red.id,
                        argument=arg_text,
                        role="blue",
                        evidence=[str(e) for e in ev_raw],
                        confidence=confidence,
                    )
                )
            if not responses:
                return None
            return responses
        except Exception as e:  # noqa: BLE001 — fallback control
            self.log.warning(
                "adversarial_pipeline.blue_llm_failed",
                error=str(e)[:120],
            )
            return None

    def _build_blue_prompt(
        self,
        draft_markdown: str,
        red: RedArgument,
    ) -> str:
        """Construye prompt para BLUE phase (defensa estructurada en JSON)."""
        return (
            "Genera una defensa estructurada (BLUE phase) para el siguiente "
            "contra-argumento RED. Identifica: argument (texto), evidence "
            "(lista de normas), confidence (0.0-1.0).\n\n"
            f"Draft: {draft_markdown}\n"
            f"RED argument (id={red.id}, target_clause={red.target_clause_index}): "
            f"{red.argument}\n\n"
            "Formato JSON: "
            '{"argument": str, "evidence": [str], "confidence": float}'
        )

    def _lookup_norm(
        self, paragraph: str
    ) -> tuple[str, list[str], float]:
        """Busca la norma aplicable al párrafo en el corpus V1.1.

        Estrategia:
        1. Si el párrafo contiene cita verificada → la usa.
        2. Si no, busca por RAG (TF-IDF) en el corpus → top-1 chunk.
        3. Si no encuentra nada → empty cite, confidence 0.4.

        Returns (cite_str, evidence, confidence).
        """
        citations = self._auditor.extract_citations(paragraph)
        verified, _unverified, _rejected = self._auditor.validate_against_corpus(
            citations
        )
        if verified:
            cite = verified[0]
            art_part = (
                f", artículo {cite.article_number}" if cite.article_number else ""
            )
            cite_str = f"{cite.document_name}{art_part}"
            return cite_str, [cite_str], 0.8

        # RAG search: top-1 chunk con score > min_score para evitar ruido
        results = self._rag.search(paragraph, k=1, min_score=0.05)
        if results:
            top = results[0]
            cite_str = (
                f"{top['document_name']}, artículo {top['article_number']}"
            )
            return cite_str, [cite_str], 0.8
        return "", [], 0.4

    # ===== Phase 3: MAGISTRADO =====

    def _magistrado_phase(
        self,
        red_arguments: list[RedArgument],
        blue_responses: list[BlueResponse],
    ) -> list[MagistradoRuling]:
        """Por cada par RED+BLUE, emite ruling.

        V2.3+ (con LLM router inyectado):
        - Por cada par RED+BLUE, prompt pidiendo JSON {ruling, reason}.
        - Si LLM responde y JSON parsea → MagistradoRuling desde el JSON.
        - Si LLM falla o JSON no parsea → fallback a rule-based (V2.2).

        V2.2 (rule-based):
        - SUSTAINED si BLUE confidence >= 0.7 y tiene evidence del corpus.
        - OVERRULED si BLUE confidence < 0.4 o sin evidence.
        - SPLIT en caso intermedio.
        """
        # V2.3+ LLM path
        if self._llm_router is not None:
            llm_rulings = self._magistrado_phase_llm(red_arguments, blue_responses)
            if llm_rulings is not None:
                return llm_rulings
            self.log.info("adversarial_pipeline.magistrado_fallback_to_rules")

        rulings: list[MagistradoRuling] = []
        blue_by_red = {b.responds_to: b for b in blue_responses}

        for red in red_arguments:
            blue = blue_by_red.get(red.id)
            if blue is None:
                rulings.append(
                    MagistradoRuling(
                        red_argument_id=red.id,
                        blue_response_id="",
                        ruling="OVERRULED",
                        reason=(
                            "BLUE no presentó defensa — RED argument se mantiene."
                        ),
                    )
                )
                continue

            if blue.confidence >= 0.7 and blue.evidence:
                ruling = "SUSTAINED"
                reason = (
                    "BLUE cita norma del corpus con confianza alta — "
                    "defensa válida, RED argument se neutraliza."
                )
            elif blue.confidence < 0.4 or not blue.evidence:
                ruling = "OVERRULED"
                reason = (
                    "BLUE no aporta evidencia del corpus o confianza baja — "
                    "RED argument prevalece."
                )
            else:
                ruling = "SPLIT"
                reason = (
                    "BLUE presenta defensa parcial — ni totalmente "
                    "fundamentada ni desestimada."
                )
            rulings.append(
                MagistradoRuling(
                    red_argument_id=red.id,
                    blue_response_id=blue.id,
                    ruling=ruling,
                    reason=reason,
                )
            )
        return rulings

    def _magistrado_phase_llm(
        self,
        red_arguments: list[RedArgument],
        blue_responses: list[BlueResponse],
    ) -> list[MagistradoRuling] | None:
        """LLM path para MAGISTRADO phase. Devuelve lista o None (fallback)."""
        try:
            blue_by_red = {b.responds_to: b for b in blue_responses}
            rulings: list[MagistradoRuling] = []
            for red in red_arguments:
                blue = blue_by_red.get(red.id)
                if blue is None:
                    # Sin BLUE → OVERRULED determinista (sin LLM necesario)
                    rulings.append(
                        MagistradoRuling(
                            red_argument_id=red.id,
                            blue_response_id="",
                            ruling="OVERRULED",
                            reason=(
                                "BLUE no presentó defensa — "
                                "RED argument se mantiene."
                            ),
                        )
                    )
                    continue
                prompt = self._build_magistrado_prompt(red, blue)
                response = self._llm_router.generate(prompt)  # type: ignore[union-attr]
                parsed = self._parse_json_object(response.text)
                ruling = str(parsed.get("ruling", "SPLIT")).upper()
                if ruling not in ("SUSTAINED", "OVERRULED", "SPLIT"):
                    ruling = "SPLIT"
                reason = str(parsed.get("reason", ""))
                rulings.append(
                    MagistradoRuling(
                        red_argument_id=red.id,
                        blue_response_id=blue.id,
                        ruling=ruling,
                        reason=reason,
                    )
                )
            if not rulings:
                return None
            return rulings
        except Exception as e:  # noqa: BLE001 — fallback control
            self.log.warning(
                "adversarial_pipeline.magistrado_llm_failed",
                error=str(e)[:120],
            )
            return None

    def _build_magistrado_prompt(
        self,
        red: RedArgument,
        blue: BlueResponse,
    ) -> str:
        """Construye prompt para MAGISTRADO phase (ruling en JSON)."""
        return (
            "Como magistrado, emite un ruling sobre el siguiente par RED+BLUE.\n"
            "ruling: SUSTAINED | OVERRULED | SPLIT\n"
            "reason: justificación breve.\n\n"
            f"RED argument (id={red.id}): {red.argument}\n"
            f"BLUE response (id={blue.id}, confidence={blue.confidence}): "
            f"{blue.argument}\n"
            f"BLUE evidence: {blue.evidence}\n\n"
            'Formato JSON: {"ruling": str, "reason": str}'
        )

    # ===== Recommendation =====

    def _recommend(
        self, rulings: list[MagistradoRuling]
    ) -> tuple[float, str]:
        """Calcula overall_strength_score y recommendation.

        - score = SUSTAINED / total
        - PROCEED_TO_FILE si score >= 0.7
        - RETRADE si 0.3 <= score < 0.7
        - ABANDON si score < 0.3

        Edge case: total == 0 (no RED arguments generados) → score 1.0,
        PROCEED_TO_FILE (vacuously: no se encontraron debilidades).
        """
        total = len(rulings)
        if total == 0:
            return 1.0, self.RECOMMEND_PROCEED
        sustained = sum(1 for r in rulings if r.ruling == "SUSTAINED")
        score = sustained / total
        if score >= 0.7:
            recommendation = self.RECOMMEND_PROCEED
        elif score >= 0.3:
            recommendation = self.RECOMMEND_RETRADE
        else:
            recommendation = self.RECOMMEND_ABANDON
        return score, recommendation

    # ===== Helpers =====

    def _split_paragraphs(self, draft_markdown: str) -> list[str]:
        """Split por '\\n\\n'. Filtra párrafos vacíos."""
        if not draft_markdown:
            return []
        return [p.strip() for p in draft_markdown.split("\n\n") if p.strip()]

    def _summarize(self, draft_markdown: str) -> str:
        """Resumen breve del draft para el resultado del pipeline."""
        paragraphs = self._split_paragraphs(draft_markdown)
        n_substantive = sum(
            1 for p in paragraphs if len(p) >= self.MIN_PARAGRAPH_LENGTH
        )
        total_chars = len(draft_markdown)
        return (
            f"Draft con {len(paragraphs)} párrafos totales, "
            f"{n_substantive} sustantivos (>= {self.MIN_PARAGRAPH_LENGTH} chars), "
            f"{total_chars} caracteres totales."
        )

    def _parse_json_list(self, text: str) -> list:
        """Extrae una lista JSON del texto del LLM.

        El LLM puede envolver el JSON en markdown fences (```json ... ```)
        o prose. Busca el primer '[' y el último ']' y parsea ese substring.

        Lanza json.JSONDecodeError o ValueError si no parsea.
        """
        if not text:
            raise json.JSONDecodeError("empty text", "", 0)
        stripped = text.strip()
        start = stripped.find("[")
        end = stripped.rfind("]")
        if start == -1 or end == -1 or end <= start:
            raise json.JSONDecodeError(
                "no JSON list brackets found", stripped, 0
            )
        json_str = stripped[start : end + 1]
        data = json.loads(json_str)
        if not isinstance(data, list):
            raise ValueError("LLM response is not a JSON list")
        return data

    def _parse_json_object(self, text: str) -> dict:
        """Extrae un objeto JSON del texto del LLM.

        Busca el primer '{' y el último '}' y parsea ese substring.
        Lanza json.JSONDecodeError o ValueError si no parsea.
        """
        if not text:
            raise json.JSONDecodeError("empty text", "", 0)
        stripped = text.strip()
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise json.JSONDecodeError(
                "no JSON object braces found", stripped, 0
            )
        json_str = stripped[start : end + 1]
        data = json.loads(json_str)
        if not isinstance(data, dict):
            raise ValueError("LLM response is not a JSON object")
        return data
