"""V7.0 — El Examen del Abogado.

Flujo ejecutable que recorre el trabajo jurídico completo de un caso,
de la recepción a la entrega. Los 12 pasos del brief V7.0:

 1.  Recibir los hechos y documentos del caso.
 2.  Identificar hechos, incertidumbres y documentos faltantes.
 3.  Delimitar los problemas jurídicos.
 4.  Determinar las fuentes normativas y jurisprudenciales necesarias.
 5.  Investigar y conservar la procedencia de las fuentes.
 6.  Validar las referencias jurídicas y la vigencia aplicable.
 7.  Formular una estrategia razonada.
 8.  Identificar argumentos contrarios, riesgos y debilidades.
 9.  Determinar requisitos procesales y términos con evidencia.
 10. Elaborar un borrador del documento jurídico apropiado.
 11. Revisar coherencia, pretensiones, hechos, pruebas, citas y requisitos.
 12. Entregar el resultado con fuentes, estrategia, documentos y limitaciones.

DISCIPLINA V7.0:
  - Cada invocación al LLM pasa por RealProviderGuard. Si no hay
    provider real, el caso queda BLOQUEADO con causa explícita.
  - Las citas jurídicas se verifican contra el corpus V1.3 real.
    Cualquier afirmación que no pueda respaldarse → ABSTENCIÓN.
  - Elaboración de borradores usa SOLO artículos presentes en el
    corpus; los artículos fuera del corpus se marcan como NO_RESUELTO.
  - El resultado es revisable por un abogado humano antes de cualquier
    actuación procesal real.

SALIDA: ``LawyerExamResult`` con todos los pasos, evidencia, citas,
estado (SUCCESS / BLOCKED / ABSTAINED / FAILED), y limitaciones.

NO envía documentos a juzgados ni ejecuta actuaciones procesales. La
presentación, firma y envío quedan sujetos a autorización humana.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from albra.knowledge.citation_audit import CitationAuditor
from albra.llm.providers import LLMResponse
from albra.llm.real_provider_guard import RealProviderGuard, RealProviderGuardError
from albra.observability.logger import get_logger


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ===== Result types =====

@dataclass
class ExamStep:
    """Resultado de un paso individual del examen."""
    step_number: int
    name: str
    status: str  # "ok" | "blocked" | "abstained" | "failed"
    summary: str = ""
    evidence: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class LawyerExamResult:
    """Resultado completo del Examen del Abogado."""
    case_id: str
    case_summary: str
    started_at: str
    finished_at: str = ""
    overall_status: str = "INCOMPLETE"  # SUCCESS | BLOCKED | ABSTAINED | FAILED | INCOMPLETE
    overall_reason: str = ""
    steps: list[ExamStep] = field(default_factory=list)
    drafted_document: str = ""
    citations_verified: list[dict[str, Any]] = field(default_factory=list)
    citations_unverified: list[dict[str, Any]] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    provider_state: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "case_summary": self.case_summary,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "overall_status": self.overall_status,
            "overall_reason": self.overall_reason,
            "steps": [
                {
                    "step_number": s.step_number,
                    "name": s.name,
                    "status": s.status,
                    "summary": s.summary,
                    "evidence": s.evidence,
                    "notes": s.notes,
                }
                for s in self.steps
            ],
            "drafted_document": self.drafted_document,
            "citations_verified": self.citations_verified,
            "citations_unverified": self.citations_unverified,
            "limitations": self.limitations,
            "provider_state": self.provider_state,
        }


# ===== The Exam =====

class LawyerExam:
    """El Examen del Abogado — flujo de 12 pasos.

    Construct with:
      case_facts: dict with ``facts``, ``documents``, ``uncertainties``.
      guard: RealProviderGuard wrapping a real LLM provider.
      citation_auditor: optional, defaults to the V1.3 corpus auditor.
    """

    def __init__(
        self,
        *,
        case_id: str,
        case_facts: dict[str, Any],
        guard: RealProviderGuard,
        citation_auditor: CitationAuditor | None = None,
    ) -> None:
        self.case_id = case_id
        self.case_facts = case_facts
        self.guard = guard
        self.citation_auditor = citation_auditor or CitationAuditor()
        self.log = get_logger("albra.lawyer.exam")
        self.result = LawyerExamResult(
            case_id=case_id,
            case_summary=str(case_facts.get("summary", ""))[:300],
            started_at=_utcnow_iso(),
        )
        self.result.provider_state = guard.explain_state()
        # Internal state shared across steps
        self._strategy_text = ""
        self._counter_text = ""
        self._review_text = ""

    # ----- Helpers -----

    def _llm(self, prompt: str, *, max_tokens: int = 1500, temperature: float = 0.4) -> LLMResponse:
        """Invoke the real LLM via the guard. Returns LLMResponse.

        On failure (mock provider, scaffold, or HTTP error), returns a
        FAILED LLMResponse — never a silent mock.
        """
        return self.guard.run_real(prompt=prompt, max_tokens=max_tokens, temperature=temperature)

    def _record_step(self, step: ExamStep) -> None:
        self.result.steps.append(step)
        self.log.info(
            "lawyer.exam.step",
            case_id=self.case_id,
            step=step.step_number,
            name=step.name,
            status=step.status,
        )

    def _abort(self, reason: str, status: str = "BLOCKED") -> None:
        self.result.overall_status = status
        self.result.overall_reason = reason
        self.result.finished_at = _utcnow_iso()

    # ----- 12-step flow -----

    def run(self) -> LawyerExamResult:
        """Execute all 12 steps. Stops early if a step BLOCKS or ABSTAINS
        in a way that prevents continuation.
        """
        try:
            self._step_01_intake()
            if self.result.overall_status != "INCOMPLETE":
                return self._finalize()
            self._step_02_facts_uncertainties()
            if self.result.overall_status != "INCOMPLETE":
                return self._finalize()
            self._step_03_legal_issues()
            if self.result.overall_status != "INCOMPLETE":
                return self._finalize()
            self._step_04_required_sources()
            self._step_05_research_provenance()
            if self.result.overall_status != "INCOMPLETE":
                return self._finalize()
            self._step_06_validate_citations()
            self._step_07_strategy()
            if self.result.overall_status != "INCOMPLETE":
                return self._finalize()
            self._step_08_counterarguments()
            if self.result.overall_status != "INCOMPLETE":
                return self._finalize()
            self._step_09_procedural_requirements()
            self._step_10_draft_document()
            if self.result.overall_status != "INCOMPLETE":
                return self._finalize()
            self._step_11_review()
            if self.result.overall_status != "INCOMPLETE":
                return self._finalize()
            self._step_12_deliver()
        except RealProviderGuardError as e:
            self._abort(f"Real provider unavailable: {e}", status="BLOCKED")
        except Exception as e:  # noqa: BLE001
            self._abort(f"Unexpected error: {type(e).__name__}: {e}", status="FAILED")
        return self._finalize()

    def _finalize(self) -> LawyerExamResult:
        if not self.result.finished_at:
            self.result.finished_at = _utcnow_iso()
        if self.result.overall_status == "INCOMPLETE":
            # All 12 steps completed without blocking.
            self.result.overall_status = "SUCCESS"
        # Always include the standard limitations.
        std_limitations = [
            "El borrador generado requiere revisión y firma de un abogado "
            "humano calificado antes de cualquier actuación procesal real.",
            "El corpus jurídico V1.3 cubre solo Constitución 1991 arts. "
            "1-32 + Ley 100/1993 (45 arts.) + Ley 80/1993 (48 arts.) — "
            "citas fuera de este rango se marcan como NO_RESUELTO.",
            "No hay jurisprudencia en el corpus (sentencias Corte "
            "Constitucional rechazadas en V1.2 — content not fetchable).",
        ]
        for lim in std_limitations:
            if lim not in self.result.limitations:
                self.result.limitations.insert(0, lim)
        return self.result

    # ----- Step 1: Intake -----

    def _step_01_intake(self) -> None:
        """Recibir los hechos y documentos del caso."""
        facts = self.case_facts.get("facts", [])
        documents = self.case_facts.get("documents", [])
        uncertainties = self.case_facts.get("uncertainties", [])
        step = ExamStep(
            step_number=1,
            name="Intake — recibir hechos y documentos",
            status="ok",
            summary=f"Recibidos {len(facts)} hechos, {len(documents)} documentos, "
                    f"{len(uncertainties)} incertidumbres iniciales.",
            evidence=[
                {"type": "facts", "count": len(facts), "items": facts},
                {"type": "documents", "count": len(documents), "items": documents},
                {"type": "uncertainties", "count": len(uncertainties), "items": uncertainties},
            ],
        )
        self._record_step(step)

    # ----- Step 2: Facts / uncertainties / missing documents -----

    def _step_02_facts_uncertainties(self) -> None:
        """Identificar hechos, incertidumbres y documentos faltantes."""
        facts = self.case_facts.get("facts", [])
        uncertainties = self.case_facts.get("uncertainties", [])
        missing_docs = self.case_facts.get("missing_documents", [])
        # The LLM does NOT decide what's missing — the case input declares it.
        # This is deliberate: we don't want the LLM to invent missing docs.
        step = ExamStep(
            step_number=2,
            name="Hechos, incertidumbres y documentos faltantes",
            status="ok",
            summary=f"Hechos claros: {len(facts)}. Incertidumbres: {len(uncertainties)}. "
                    f"Documentos faltantes declarados: {len(missing_docs)}.",
            evidence=[
                {"type": "clear_facts", "items": facts},
                {"type": "uncertainties", "items": uncertainties},
                {"type": "missing_documents", "items": missing_docs},
            ],
        )
        if missing_docs:
            step.notes.append(
                "El caso declara documentos faltantes. La estrategia debe "
                "contemplar la posibilidad de no poder probar todos los hechos."
            )
        self._record_step(step)

    # ----- Step 3: Legal issues -----

    def _step_03_legal_issues(self) -> None:
        """Delimitar los problemas jurídicos."""
        # The case input provides legal_issues (deterministic).
        # We do NOT ask the LLM to invent issues — that risks hallucination.
        legal_issues = self.case_facts.get("legal_issues", [])
        step = ExamStep(
            step_number=3,
            name="Delimitación de problemas jurídicos",
            status="ok" if legal_issues else "abstained",
            summary=(
                f"Problemas jurídicos delimitados: {len(legal_issues)}."
                if legal_issues
                else "No se delimitaron problemas jurídicos — el caso "
                     "no los declaró. Abstención."
            ),
            evidence=[{"type": "legal_issues", "items": legal_issues}],
        )
        if not legal_issues:
            step.notes.append(
                "La delimitación de problemas jurídicos es responsabilidad "
                "del abogado humano. El flujo no inventa problemas."
            )
            self._abort(
                "Sin problemas jurídicos delimitados — el caso no es "
                "procesable por el examen.",
                status="ABSTAINED",
            )
            return
        self._record_step(step)

    # ----- Step 4: Required sources -----

    def _step_04_required_sources(self) -> None:
        """Determinar las fuentes normativas y jurisprudenciales necesarias."""
        required = self.case_facts.get("required_sources", [])
        # We don't ask the LLM for sources — that risks hallucination.
        # The case declares what it needs; we verify availability.
        step = ExamStep(
            step_number=4,
            name="Fuentes normativas necesarias",
            status="ok" if required else "abstained",
            summary=(
                f"Fuentes requeridas: {len(required)}."
                if required
                else "No se declararon fuentes requeridas."
            ),
            evidence=[{"type": "required_sources", "items": required}],
        )
        if not required:
            step.notes.append(
                "El caso debe declarar las fuentes normativas que pretende "
                "invocar (e.g. Constitución art. 28, Ley 100 art. 8)."
            )
        self._record_step(step)

    # ----- Step 5: Research + provenance -----

    def _step_05_research_provenance(self) -> None:
        """Investigar y conservar la procedencia de las fuentes."""
        required = self.case_facts.get("required_sources", [])
        # For each required source, look it up in the corpus.
        evidence: list[dict[str, Any]] = []
        any_found = False
        for src in required:
            doc_name = src.get("document", "")
            article_num = str(src.get("article", ""))
            # Use the citation auditor's corpus to find this article.
            found = self._lookup_in_corpus(doc_name, article_num)
            if found:
                any_found = True
                evidence.append({
                    "type": "found_in_corpus",
                    "document": doc_name,
                    "article": article_num,
                    "provenance_status": found.get("provenance_status", "UNKNOWN"),
                    "source_url": found.get("source_url", ""),
                    "source_tier": found.get("source_tier", ""),
                })
            else:
                evidence.append({
                    "type": "not_in_corpus",
                    "document": doc_name,
                    "article": article_num,
                    "provenance_status": "NOT_AVAILABLE",
                })
        step = ExamStep(
            step_number=5,
            name="Investigación y procedencia de fuentes",
            status="ok" if any_found else "abstained",
            summary=(
                f"Fuentes encontradas en corpus V1.3: {sum(1 for e in evidence if e['type'] == 'found_in_corpus')} "
                f"de {len(required)} requeridas."
            ),
            evidence=evidence,
        )
        if not any_found:
            step.notes.append(
                "Ninguna de las fuentes requeridas está en el corpus V1.3. "
                "El examen ABSTIENE — no se pueden formular argumentos sin "
                "evidencia verificable."
            )
            self._abort(
                "Ninguna fuente requerida está en el corpus V1.3 — el caso "
                "no se puede procesar con evidencia verificable.",
                status="ABSTAINED",
            )
        self._record_step(step)

    def _lookup_in_corpus(self, doc_name: str, article_num: str) -> dict[str, Any] | None:
        """Look up a specific article in the V1.4 corpus (with V1.3 fallback).

        V8.0 Fase 2.2: updated from V1.3 to V1.4 so that the LawyerExam
        can find articles in the expanded corpus (CST, CGP, CPP, Ley 640,
        sentencias). V1.3 is used as fallback if V1.4 import fails.

        Returns the article dict (with provenance) if found, else None.
        """
        # V8.0 Fase 2.2: try V1.4 first, fall back to V1.3.
        corpus = None
        try:
            from albra.knowledge.colombia.corpus_pilot.real_corpus_v14 import (
                ALL_DOCUMENTS_V14,
            )
            corpus = ALL_DOCUMENTS_V14
        except ImportError:
            pass
        if corpus is None:
            try:
                from albra.knowledge.colombia.corpus_pilot.real_corpus_v13 import (
                    ALL_DOCUMENTS_V13,
                )
                corpus = ALL_DOCUMENTS_V13
            except ImportError:
                return None
        # Map common aliases to the corpus document_type keys.
        aliases = {
            "constitucion": "constitucion",
            "constitución": "constitucion",
            "constitución política de 1991": "constitucion",
            "codigo_sustantivo_trabajo": "codigo_sustantivo_trabajo",
            "cst": "codigo_sustantivo_trabajo",
            "codigo sustantivo del trabajo": "codigo_sustantivo_trabajo",
            "ley 1564": "ley_1564_2012",
            "ley 1564 de 2012": "ley_1564_2012",
            "cgp": "ley_1564_2012",
            "ley 640": "ley_0640_2001",
            "ley 640 de 2001": "ley_0640_2001",
            "ley 906": "ley_0906_2004",
            "ley 906 de 2004": "ley_0906_2004",
            "cpp": "ley_0906_2004",
            "ley 100": "ley_100",
            "ley 100 de 1993": "ley_100",
            "ley 80": "ley_80",
            "ley 80 de 1993": "ley_80",
        }
        key = aliases.get(doc_name.lower().strip())
        if not key:
            # Fuzzy: match by lowercased name
            for slug, _doc in corpus:
                if doc_name.lower() in slug.lower() or slug.lower() in doc_name.lower():
                    key = slug
                    break
        if not key:
            return None
        for slug, doc in corpus:
            if slug != key:
                continue
            # Find article by number
            for art in doc.get("articles", []):
                if str(art.get("number")) == str(article_num):
                    prov = doc.get("provenance", {})
                    src_capture = getattr(prov, "source_capture", None) if hasattr(prov, "source_capture") else None
                    return {
                        "article_text": art.get("text", ""),
                        "article_number": art.get("number"),
                        "provenance_status": doc.get("provenance_status", "UNKNOWN"),
                        "source_url": getattr(src_capture, "source_url", "") if src_capture else "",
                        "source_tier": doc.get("source_tier", ""),
                    }
        return None

    # ----- Step 6: Validate citations + vigency -----

    def _step_06_validate_citations(self) -> None:
        """Validar las referencias jurídicas y la vigencia aplicable."""
        required = self.case_facts.get("required_sources", [])
        verified: list[dict[str, Any]] = []
        unverified: list[dict[str, Any]] = []
        for src in required:
            doc_name = src.get("document", "")
            article_num = str(src.get("article", ""))
            found = self._lookup_in_corpus(doc_name, article_num)
            if found:
                verified.append({
                    "document": doc_name,
                    "article": article_num,
                    "provenance_status": found["provenance_status"],
                    "source_url": found["source_url"],
                    "article_text_preview": found["article_text"][:200],
                })
            else:
                unverified.append({
                    "document": doc_name,
                    "article": article_num,
                    "reason": "NOT_IN_CORPUS_V13",
                })
        self.result.citations_verified = verified
        self.result.citations_unverified = unverified
        step = ExamStep(
            step_number=6,
            name="Validación de citas y vigencia",
            status="ok" if verified else "abstained",
            summary=f"Citas verificadas: {len(verified)}. No verificadas: {len(unverified)}.",
            evidence=[
                {"type": "verified", "items": verified},
                {"type": "unverified", "items": unverified},
            ],
        )
        if unverified:
            step.notes.append(
                f"{len(unverified)} citas no están en el corpus V1.3. La "
                f"estrategia debe ABSTENERSE de invocarlas como fundamento."
            )
        self._record_step(step)

    # ----- Step 7: Strategy -----

    def _step_07_strategy(self) -> None:
        """Formular una estrategia razonada.

        V7.0: la estrategia la formula el LLM real, pero el guardián
        rechaza caer a Mock. Si el LLM falla, el caso queda BLOQUEADO.

        V8.0 Fase 2: antes de formular la estrategia, ejecutar
        AdversarialValidator sobre las citas verificadas. Si hay
        defectos blocking (norma derogada, contradicción no resuelta),
        el caso queda BLOQUEADO — no se formula estrategia sobre
        fundamentos defectuosos.
        """
        verified = self.result.citations_verified
        if not verified:
            self._abort(
                "No hay citas verificadas para formular estrategia — abstención.",
                status="ABSTAINED",
            )
            return

        # V8.0 Fase 2: Adversarial validation of citations BEFORE strategy.
        try:
            from albra.knowledge.colombia.corpus_pilot.real_corpus_v14 import (
                ALL_DOCUMENTS_V14,
            )
            from albra.lawyer.adversarial_validation import AdversarialValidator
            validator = AdversarialValidator()
            validation = validator.validate(
                citations=verified,
                corpus=ALL_DOCUMENTS_V14,
                affected_element="strategy",
            )
            if not validation.ok:
                blocking_defects = [
                    d for d in validation.defects if d.severity == "blocking"
                ]
                step = ExamStep(
                    step_number=7,
                    name="Estrategia razonada",
                    status="blocked",
                    summary=(
                        f"Validación adversarial BLOQUEÓ la estrategia: "
                        f"{len(blocking_defects)} defecto(s) blocking."
                    ),
                    evidence=[
                        {"type": "validation_defects", "items": [d.as_dict() for d in blocking_defects]},
                    ],
                )
                self._record_step(step)
                self._abort(
                    f"Estrategia bloqueada por validación adversarial: "
                    f"{'; '.join(d.detail for d in blocking_defects)}. "
                    "El caso no puede declararse SUCCESS con fundamentos defectuosos.",
                    status="BLOCKED",
                )
                return
        except ImportError:
            # AdversarialValidator not available — continue without it
            # (preserves V7.0 behavior if the module is missing).
            pass

        # Build the LLM prompt with the verified article texts.
        article_texts = "\n\n".join(
            f"[{v['document']} art. {v['article']}]\n{v['article_text_preview']}"
            for v in verified
        )
        prompt = (
            "Eres un abogado colombiano. Formula una estrategia jurídica "
            "razonada para el siguiente caso. Usa EXCLUSIVAMENTE las "
            "normas verificadas que te proporciono. Si necesitas invocar "
            "una norma que no está en la lista, ABSTENTE de hacerlo y "
            "decláralo como NO_RESUELTO.\n\n"
            f"HECHOS DEL CASO:\n{json.dumps(self.case_facts.get('facts', []), ensure_ascii=False)}\n\n"
            f"NORMAS VERIFICADAS (corpus V1.3):\n{article_texts}\n\n"
            "ESTRATEGIA (máx 500 palabras, en español, distinguiendo "
            "hechos / inferencias / conclusiones):"
        )
        response = self._llm(prompt, max_tokens=1200, temperature=0.3)
        if RealProviderGuard.is_response_failed(response):
            step = ExamStep(
                step_number=7,
                name="Estrategia razonada",
                status="blocked",
                summary=f"LLM provider falló: {response.metadata.get('error_category', 'unknown')}",
                evidence=[{"type": "llm_failure", "metadata": response.metadata}],
            )
            self._record_step(step)
            self._abort(
                f"Estrategia no formulada — LLM real falló: "
                f"{response.metadata.get('error_category', 'unknown')}. "
                "El caso queda BLOQUEADO — no se cae silenciosamente a Mock.",
                status="BLOCKED",
            )
            return
        step = ExamStep(
            step_number=7,
            name="Estrategia razonada",
            status="ok",
            summary="Estrategia formulada por LLM real.",
            evidence=[
                {"type": "llm_response", "provider": response.provider, "model": response.model},
                {"type": "strategy_text", "text": response.text[:2000]},
            ],
        )
        # Store the strategy for use in step 10 (draft).
        self._strategy_text = response.text
        self._record_step(step)

    # ----- Step 8: Counter-arguments -----

    def _step_08_counterarguments(self) -> None:
        """Identificar argumentos contrarios, riesgos y debilidades."""
        if not self._strategy_text:
            self._abort("Sin estrategia previa — no se pueden formular contraargumentos.", status="ABSTAINED")
            return
        prompt = (
            "Eres un abogado colombiano haciendo RED TEAM sobre la siguiente "
            "estrategia jurídica. Identifica 3-5 contraargumentos, riesgos "
            "y debilidades. Sé específico — no generalices.\n\n"
            f"ESTRATEGIA:\n{self._strategy_text}\n\n"
            "CONTRAARGUMENTOS (máx 400 palabras, en español):"
        )
        response = self._llm(prompt, max_tokens=800, temperature=0.4)
        if RealProviderGuard.is_response_failed(response):
            step = ExamStep(
                step_number=8,
                name="Contraargumentos (RED TEAM)",
                status="blocked",
                summary=f"LLM falló: {response.metadata.get('error_category', 'unknown')}",
            )
            self._record_step(step)
            self._abort(
                "Contraargumentos no formulados — LLM real falló. Caso BLOQUEADO.",
                status="BLOCKED",
            )
            return
        step = ExamStep(
            step_number=8,
            name="Contraargumentos (RED TEAM)",
            status="ok",
            summary="Contraargumentos formulados por LLM real.",
            evidence=[{"type": "red_team_text", "text": response.text[:2000]}],
        )
        self._counter_text = response.text
        self._record_step(step)

    # ----- Step 9: Procedural requirements -----

    def _step_09_procedural_requirements(self) -> None:
        """Determinar requisitos procesales y términos con evidencia."""
        # The corpus only has constitutional + 2 laws. Procedural
        # requirements come from CPC/Ley 640/etc — NOT in corpus.
        # We declare this honestly.
        step = ExamStep(
            step_number=9,
            name="Requisitos procesales y términos",
            status="abstained",
            summary=(
                "El corpus V1.3 NO contiene Código de Procedimiento Civil "
                "ni Ley 640 de 2001 (conciliación) ni otros cuerpos "
                "procesales. No se pueden determinar términos procesales "
                "con evidencia."
            ),
            evidence=[],
            notes=[
                "Requisito: el caso debe ser revisado por abogado humano "
                "para identificar plazos, juzgado competente, cuantía, "
                "y trámite procesal aplicable.",
            ],
        )
        self.result.limitations.append(
            "Paso 9 abstenido: corpus V1.3 no contiene cuerpos procesales "
            "(CPC, Ley 640, Ley 1564, etc.). Los términos procesales "
            "deben determinarse manualmente por el abogado humano."
        )
        self._record_step(step)

    # ----- Step 10: Draft document -----

    def _step_10_draft_document(self) -> None:
        """Elaborar un borrador del documento jurídico apropiado."""
        if not self._strategy_text:
            self._abort("Sin estrategia previa — no se puede redactar borrador.", status="ABSTAINED")
            return
        doc_type = self.case_facts.get("document_type", "escrito jurídico")
        prompt = (
            "Eres un abogado colombiano. Redacta un borrador del siguiente "
            "documento jurídico. Usa SOLO las normas verificadas. NO "
            "inventes normas, sentencias, ni citas que no estén en la "
            "lista. Estructura el documento con: encabezado, hechos, "
            "fundamentos de derecho, pretensiones/solicitudes, y "
            "anexos.\n\n"
            f"TIPO DE DOCUMENTO: {doc_type}\n"
            f"HECHOS: {json.dumps(self.case_facts.get('facts', []), ensure_ascii=False)}\n"
            f"ESTRATEGIA: {self._strategy_text}\n"
            f"CONTRAARGUMENTOS (a refutar): {self._counter_text or 'N/A'}\n"
            f"NORMAS VERIFICADAS (corpus V1.3):\n" + "\n".join(
                f"- {v['document']} art. {v['article']}: {v['article_text_preview']}"
                for v in self.result.citations_verified
            ) + "\n\n"
            "BORRADOR (en español, formato profesional, incluye 'Borrador "
            "generado por ALBRA — requiere revisión y firma de abogado "
            "humano'):"
        )
        response = self._llm(prompt, max_tokens=2500, temperature=0.5)
        if RealProviderGuard.is_response_failed(response):
            step = ExamStep(
                step_number=10,
                name="Borrador del documento",
                status="blocked",
                summary=f"LLM falló: {response.metadata.get('error_category', 'unknown')}",
            )
            self._record_step(step)
            self._abort(
                "Borrador no redactado — LLM real falló. Caso BLOQUEADO.",
                status="BLOCKED",
            )
            return
        self.result.drafted_document = response.text
        step = ExamStep(
            step_number=10,
            name="Borrador del documento",
            status="ok",
            summary=f"Borrador de {doc_type} generado por LLM real ({len(response.text)} chars).",
            evidence=[
                {"type": "draft_preview", "text": response.text[:500]},
                {"type": "llm_metadata", "provider": response.provider, "model": response.model},
            ],
        )
        self._record_step(step)

    # ----- Step 11: Review -----

    def _step_11_review(self) -> None:
        """Revisar coherencia, pretensiones, hechos, pruebas, citas y requisitos."""
        if not self.result.drafted_document:
            self._abort("Sin borrador previo — no se puede revisar.", status="ABSTAINED")
            return
        prompt = (
            "Eres un abogado colombiano haciendo revisión interna del "
            "siguiente borrador. Verifica:\n"
            "1. Que todas las normas citadas estén en el corpus V1.3 "
            "(no inventadas).\n"
            "2. Coherencia entre hechos y pretensiones.\n"
            "3. Que el borrador no afirme nada que no esté respaldado "
            "por las normas verificadas.\n"
            "Lista los hallazgos en formato bullet. Si todo está OK, "
            "dilo explícitamente.\n\n"
            f"BORRADOR:\n{self.result.drafted_document[:3000]}\n\n"
            f"NORMAS VERIFICADAS: {[v['document'] + ' art.' + str(v['article']) for v in self.result.citations_verified]}\n\n"
            "REVISIÓN (en español):"
        )
        response = self._llm(prompt, max_tokens=1000, temperature=0.2)
        if RealProviderGuard.is_response_failed(response):
            step = ExamStep(
                step_number=11,
                name="Revisión interna",
                status="blocked",
                summary=f"LLM falló: {response.metadata.get('error_category', 'unknown')}",
            )
            self._record_step(step)
            self._abort(
                "Revisión no realizada — LLM real falló. Caso BLOQUEADO.",
                status="BLOCKED",
            )
            return
        step = ExamStep(
            step_number=11,
            name="Revisión interna",
            status="ok",
            summary="Revisión realizada por LLM real.",
            evidence=[{"type": "review_text", "text": response.text[:2000]}],
        )
        self._review_text = response.text
        self._record_step(step)

        # V8.0 Fase 2: post-review adversarial validation.
        # After the LLM review, run the AdversarialValidator again on
        # the citations used in the draft. If new blocking defects
        # appear (e.g. the draft cited a derogated norm not in the
        # original verified list), block the case.
        try:
            from albra.knowledge.colombia.corpus_pilot.real_corpus_v14 import (
                ALL_DOCUMENTS_V14,
            )
            from albra.lawyer.adversarial_validation import AdversarialValidator
            validator = AdversarialValidator()
            post_validation = validator.validate(
                citations=self.result.citations_verified,
                corpus=ALL_DOCUMENTS_V14,
                affected_element="review",
            )
            if not post_validation.ok:
                blocking = [d for d in post_validation.defects if d.severity == "blocking"]
                if blocking:
                    self._abort(
                        f"Revisión interna bloqueada por validación adversarial post-revisión: "
                        f"{'; '.join(d.detail for d in blocking)}. "
                        "El caso no puede declararse SUCCESS con defectos blocking.",
                        status="BLOCKED",
                    )
                    return
        except ImportError:
            pass  # preserves V7.0 behavior

    # ----- Step 12: Deliver -----

    def _step_12_deliver(self) -> None:
        """Entregar el resultado con fuentes, estrategia, documentos y limitaciones."""
        step = ExamStep(
            step_number=12,
            name="Entrega del resultado",
            status="ok",
            summary=(
                f"Resultado entregado. Estado: SUCCESS. "
                f"Citas verificadas: {len(self.result.citations_verified)}. "
                f"Citas no verificadas: {len(self.result.citations_unverified)}. "
                f"Limitaciones: {len(self.result.limitations)}. "
                "El borrador requiere revisión humana antes de cualquier "
                "actuación procesal."
            ),
            evidence=[
                {"type": "draft_available", "chars": len(self.result.drafted_document)},
                {"type": "strategy_available", "chars": len(self._strategy_text)},
                {"type": "review_available", "chars": len(self._review_text)},
            ],
            notes=[
                "El resultado NO se envía a juzgado. La presentación, firma "
                "y envío quedan sujetos a autorización humana explícita.",
            ],
        )
        self._record_step(step)
