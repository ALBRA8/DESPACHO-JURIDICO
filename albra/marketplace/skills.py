"""
SKILLS MARKETPLACE — catálogo público de skills de ALBRA consumibles vía MCP.

Inspiración clean-room: Agent Skills for Legal (969+ skills, Find→Copy→Use,
MCP integration), case.dev (880+ portable skills, se van con el firm).

V2.5-A: skills como dataclasses + registry local. V2.5+: HTTP server público
con OAuth + rate limiting (V2.4-B McpServer ya expone tools, este módulo
los INDEXA como skills descubribles).

Cada skill:
- id: kebab-case único
- name: display name
- description: qué hace
- category: drafting | review | research | analysis | compliance | deadline
- practice_areas: list[str] (civil, laboral, etc.)
- mcp_tool_name: tool MCP que la expone (cualquiera de los 10 de V2.3-B)
- input_schema: dict JSON schema
- output_type: str (dict | list | str)
- version: str (semver)
- author: str (default "ALBRA")
- license: str (default "Apache-2.0")
- tags: list[str]
- examples: list[dict] (input → output samples)

API:
- register_skill(skill: Skill) -> str
- list_skills(category=None, practice_area=None, tag=None) -> list[Skill]
- get_skill(id) -> Skill | None
- search_skills(query) -> list[Skill] (substring search on name/description/tags)
- export_catalog() -> list[dict] (todas las skills como dict para MCP discovery)
- stats() -> {total_skills, by_category, by_practice_area, by_author}

Bootstrap automático: 5 agentes de V2.0 + 5 playbooks de V2.2-D + 5 tools
avanzadas (CitationAuditor, LocalRAG, DeadlineGuard, AgenticCitator,
PrecedentBoard) = 15 skills pre-registradas.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from albra.observability.logger import get_logger

__all__ = [
    "Skill",
    "SkillValidationError",
    "SkillsMarketplace",
    "get_marketplace",
    "reset_marketplace",
]


_VALID_CATEGORIES: frozenset[str] = frozenset({
    "drafting", "review", "research", "analysis", "compliance", "deadline",
})

_VALID_OUTPUT_TYPES: frozenset[str] = frozenset({"dict", "list", "str"})

# Las 7 áreas de práctica del despacho (consistente con AgentLoader V2.0).
_ALL_PRACTICE_AREAS: list[str] = [
    "civil",
    "constitucional",
    "laboral",
    "penal",
    "corporativo",
    "administrativo",
    "familia",
]


class SkillValidationError(ValueError):
    """Levantado cuando una Skill es inválida o duplicada."""


@dataclass
class Skill:
    """Definición de una skill ALBRA consumible vía MCP.

    Cada skill indexa una capability del despacho (agente, playbook o tool
    avanzada) y la expone como unidad descubrible + invocable a través del
    McpServer público V2.3-B. Inspirado en Agent Skills for Legal
    (Find→Copy→Use) y case.dev (880+ portable skills).
    """

    id: str
    name: str
    description: str
    category: str
    practice_areas: list[str]
    mcp_tool_name: str
    input_schema: dict[str, Any]
    output_type: str
    version: str = "1.0.0"
    author: str = "ALBRA"
    license: str = "Apache-2.0"
    tags: list[str] = field(default_factory=list)
    examples: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """Serializa la skill para MCP discovery (catalog + list_tools)."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "practice_areas": list(self.practice_areas),
            "mcp_tool_name": self.mcp_tool_name,
            "input_schema": dict(self.input_schema),
            "output_type": self.output_type,
            "version": self.version,
            "author": self.author,
            "license": self.license,
            "tags": list(self.tags),
            "examples": [dict(e) for e in self.examples],
        }


class SkillsMarketplace:
    """Registry local de skills ALBRA.

    V2.5-A: registry en memoria (pure Python, no DB). V2.5+: HTTP server público
    con OAuth + rate limiting (storage persistente opcional). El registry indexa
    skills consumibles vía las 10 tools del McpServer público V2.3-B.

    Usage::

        mp = SkillsMarketplace()
        mp.list_skills(category="drafting")
        mp.get_skill("intake-agent")
        mp.search_skills("citation")
        mp.export_catalog()  # → MCP discovery
    """

    def __init__(self) -> None:
        self.log = get_logger("albra.marketplace")
        self._skills: dict[str, Skill] = {}
        self._bootstrap()

    # ===== Registration =====

    def register_skill(self, skill: Skill) -> str:
        """Registra una skill. Devuelve su id.

        Raises:
            SkillValidationError: si la skill está duplicada o le faltan
                campos obligatorios, o si category/output_type son inválidos.
        """
        # Campos obligatorios no vacíos (strings + listas + dict)
        required_scalar: tuple[str, ...] = (
            "id",
            "name",
            "description",
            "category",
            "mcp_tool_name",
            "output_type",
        )
        for fname in required_scalar:
            val = getattr(skill, fname)
            if not val:
                raise SkillValidationError(
                    f"Skill missing required field: {fname}"
                )
        if not skill.practice_areas:
            raise SkillValidationError(
                "Skill missing required field: practice_areas"
            )
        if not skill.input_schema:
            raise SkillValidationError(
                "Skill missing required field: input_schema"
            )

        # Validación enum
        if skill.category not in _VALID_CATEGORIES:
            raise SkillValidationError(
                f"Skill '{skill.id}' has invalid category "
                f"'{skill.category}'. Valid: {sorted(_VALID_CATEGORIES)}"
            )
        if skill.output_type not in _VALID_OUTPUT_TYPES:
            raise SkillValidationError(
                f"Skill '{skill.id}' has invalid output_type "
                f"'{skill.output_type}'. Valid: {sorted(_VALID_OUTPUT_TYPES)}"
            )

        # Duplicado
        if skill.id in self._skills:
            raise SkillValidationError(
                f"Skill with id '{skill.id}' already registered"
            )

        self._skills[skill.id] = skill
        self.log.info(
            "marketplace.skill.registered",
            skill_id=skill.id,
            category=skill.category,
            mcp_tool=skill.mcp_tool_name,
        )
        return skill.id

    # ===== Discovery =====

    def list_skills(
        self,
        *,
        category: str | None = None,
        practice_area: str | None = None,
        tag: str | None = None,
    ) -> list[Skill]:
        """Lista skills con filtros opcionales por category/practice_area/tag.

        Los tres filtros son AND (si se pasan varios, todos deben cumplirse).
        Sin filtros devuelve las 15 skills bootstrapped + las registradas
        manualmente.
        """
        result: list[Skill] = []
        for skill in self._skills.values():
            if category is not None and skill.category != category:
                continue
            if practice_area is not None and practice_area not in skill.practice_areas:
                continue
            if tag is not None and tag not in skill.tags:
                continue
            result.append(skill)
        return result

    def get_skill(self, skill_id: str) -> Skill | None:
        """Devuelve la Skill con ese id, o None si no existe."""
        return self._skills.get(skill_id)

    def search_skills(self, query: str) -> list[Skill]:
        """Substring search case-insensitive en name/description/tags.

        Devuelve todas las skills cuyo name, description o alguno de sus tags
        contiene el query como substring (case-insensitive).
        """
        if not query or not query.strip():
            return []
        q = query.strip().lower()
        result: list[Skill] = []
        for skill in self._skills.values():
            haystack = " ".join(
                [skill.name, skill.description, *skill.tags]
            ).lower()
            if q in haystack:
                result.append(skill)
        return result

    def export_catalog(self) -> list[dict[str, Any]]:
        """Devuelve todas las skills como dict para MCP discovery.

        Útil para que un MCP client (Claude Desktop, CourtListener MCP,
        Moonlit Legal Research MCP) haga ``tools/list`` y obtenga el
        catálogo completo de skills ALBRA descubribles.
        """
        return [s.as_dict() for s in self._skills.values()]

    def stats(self) -> dict[str, Any]:
        """Devuelve métricas agregadas del registry.

        Returns:
            dict con keys:
                - total_skills: int
                - by_category: dict[str, int]
                - by_practice_area: dict[str, int]
                - by_author: dict[str, int]
        """
        by_category: dict[str, int] = {}
        by_practice_area: dict[str, int] = {}
        by_author: dict[str, int] = {}
        for skill in self._skills.values():
            by_category[skill.category] = by_category.get(skill.category, 0) + 1
            by_author[skill.author] = by_author.get(skill.author, 0) + 1
            for area in skill.practice_areas:
                by_practice_area[area] = by_practice_area.get(area, 0) + 1
        return {
            "total_skills": len(self._skills),
            "by_category": by_category,
            "by_practice_area": by_practice_area,
            "by_author": by_author,
        }

    def reset(self) -> None:
        """Vacía el registry. Útil para tests."""
        self._skills.clear()
        self.log.info("marketplace.reset")

    # ===== Bootstrap =====

    def _bootstrap(self) -> None:
        """Registra las 15 skills por defecto (5 agentes + 5 playbooks + 5 tools)."""
        for skill in _build_default_skills():
            if skill.id in self._skills:
                continue
            try:
                self.register_skill(skill)
            except SkillValidationError as e:
                self.log.error(
                    "marketplace.bootstrap.failed",
                    skill_id=skill.id,
                    error=str(e),
                )
                raise


# =========================================================================
# BOOTSTRAP: 15 skills pre-registradas (5 agentes + 5 playbooks + 5 tools)
# =========================================================================


def _build_default_skills() -> list[Skill]:
    """Construye las 15 skills por defecto inspiradas en agentskills.legal."""
    skills: list[Skill] = []
    skills.extend(_build_agent_skills())
    skills.extend(_build_playbook_skills())
    skills.extend(_build_advanced_tool_skills())
    return skills


def _build_agent_skills() -> list[Skill]:
    """5 skills indexando los agentes del organigrama (V2.0).

    Cada agente del despacho (intake / research / drafting / review / filing)
    se expone como skill consumible vía una de las 10 tools MCP del V2.3-B.
    """
    return [
        Skill(
            id="intake-agent",
            name="Intake Agent Skill",
            description=(
                "Recopila y estructura datos del cliente al inicio de un matter: "
                "identificación, parties, área de práctica, deadlines procesales. "
                "Avanza el state machine NUEVO → INTAKE y persiste en MatterStore."
            ),
            category="research",
            practice_areas=list(_ALL_PRACTICE_AREAS),
            mcp_tool_name="advance_matter",
            input_schema={
                "type": "object",
                "properties": {
                    "matter_id": {"type": "string"},
                    "target_state": {"type": "string", "default": "INTAKE"},
                    "by": {"type": "string", "default": "intake-agent"},
                    "reason": {"type": "string"},
                },
                "required": ["matter_id", "target_state"],
            },
            output_type="dict",
            tags=["intake", "client-data", "matter-creation", "agent"],
            examples=[
                {
                    "input": {"matter_id": "m-001", "target_state": "INTAKE"},
                    "output": {"ok": True, "state": "INTAKE", "by": "intake-agent"},
                },
            ],
        ),
        Skill(
            id="research-agent",
            name="Research Agent Skill",
            description=(
                "Research jurídica sobre el corpus ALBRA (Constitución 1991, "
                "Ley 100/1993, Ley 80/1993) con TF-IDF + cosine. Devuelve top-k "
                "chunks relevantes para fundamentar pretensiones y contestaciones."
            ),
            category="research",
            practice_areas=list(_ALL_PRACTICE_AREAS),
            mcp_tool_name="search_corpus",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "k": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
            output_type="list",
            tags=["research", "jurisprudence", "corpus", "rag", "agent"],
            examples=[
                {
                    "input": {"query": "salud artículo 13", "k": 3},
                    "output": [{"chunk_id": "const-1991-art-13", "score": 0.42}],
                },
            ],
        ),
        Skill(
            id="drafting-agent",
            name="Drafting Agent Skill",
            description=(
                "Redacta documentos legales (poderes, demandas, tutelas, contratos) "
                "siguiendo el playbook del área de práctica. Cumple rubrics "
                "V2.3-A (essential + forbidden + bonus clauses)."
            ),
            category="drafting",
            practice_areas=list(_ALL_PRACTICE_AREAS),
            mcp_tool_name="get_playbook",
            input_schema={
                "type": "object",
                "properties": {
                    "practice_area": {"type": "string"},
                },
                "required": ["practice_area"],
            },
            output_type="dict",
            tags=["drafting", "documents", "demanda", "tutela", "agent"],
            examples=[
                {
                    "input": {"practice_area": "laboral"},
                    "output": {
                        "practice_area": "laboral",
                        "required_documents": ["poder_judicial.docx"],
                    },
                },
            ],
        ),
        Skill(
            id="review-agent",
            name="Review Agent Skill",
            description=(
                "Revisa documentos generados por Drafting-Agent contra rubrics "
                "V2.3-A y corpus V1.1. Audita citas y bloquea phantom citations "
                "antes de enviar al cliente."
            ),
            category="review",
            practice_areas=list(_ALL_PRACTICE_AREAS),
            mcp_tool_name="run_eval_suite",
            input_schema={"type": "object", "properties": {}, "required": []},
            output_type="dict",
            tags=["review", "compliance", "audit", "rubrics", "agent"],
            examples=[
                {
                    "input": {},
                    "output": {"rubrics_passed": 3, "phantom_tpr": 1.0},
                },
            ],
        ),
        Skill(
            id="filing-agent",
            name="Filing Agent Skill",
            description=(
                "Leadership tier del organigrama. Firma y radica actuaciones "
                "ante la jurisdicción correspondiente. Requiere "
                "minimum_human_signoff=1 antes de presentar cualquier documento "
                "al despacho judicial."
            ),
            category="compliance",
            practice_areas=list(_ALL_PRACTICE_AREAS),
            mcp_tool_name="verify_audit_chain",
            input_schema={
                "type": "object",
                "properties": {"matter_id": {"type": "string"}},
                "required": ["matter_id"],
            },
            output_type="dict",
            tags=["filing", "court", "submission", "signoff", "agent"],
            examples=[
                {
                    "input": {"matter_id": "m-001"},
                    "output": {"ok": True, "total": 5, "broken_at": None},
                },
            ],
        ),
    ]


def _build_playbook_skills() -> list[Skill]:
    """5 skills indexando los playbooks por área de práctica (V2.2-D)."""
    playbook_defs: list[tuple[str, str, list[str]]] = [
        (
            "civil",
            "Prescripción civil extracontractual + contestación de demanda",
            ["prescripcion_civil_extracontractual", "demanda_contestacion"],
        ),
        (
            "laboral",
            "Prescripción laboral 3 años + recursos de sentencia",
            ["prescripcion_laboral_3_years", "recursos_sentencia"],
        ),
        (
            "constitucional",
            "Tutela presentación + impugnación de sentencia",
            ["tutela_presentacion", "impugnacion_sentencia"],
        ),
        (
            "familia",
            "Prescripción civil + contestación de demanda familiar",
            ["prescripcion_civil_extracontractual", "demanda_contestacion"],
        ),
        (
            "corporativo",
            "Prescripción contractual civil",
            ["prescripcion_civil_contractual"],
        ),
    ]
    skills: list[Skill] = []
    for area, deadline_summary, deadline_types in playbook_defs:
        skills.append(
            Skill(
                id=f"{area}-playbook",
                name=f"{area.capitalize()} Playbook Skill",
                description=(
                    f"Playbook del área {area}: workflow_states, "
                    f"required_documents, deadline_types ({deadline_summary}), "
                    f"citation_corpus y red_flags. Guía para DRAFTING-AGENT "
                    f"y REVIEW-AGENT en matters de {area}."
                ),
                category="drafting",
                practice_areas=[area],
                mcp_tool_name="get_playbook",
                input_schema={
                    "type": "object",
                    "properties": {
                        "practice_area": {
                            "type": "string",
                            "default": area,
                        },
                    },
                    "required": ["practice_area"],
                },
                output_type="dict",
                tags=["playbook", area],
                examples=[
                    {
                        "input": {"practice_area": area},
                        "output": {
                            "practice_area": area,
                            "deadline_types": deadline_types,
                        },
                    },
                ],
            )
        )
    return skills


def _build_advanced_tool_skills() -> list[Skill]:
    """5 skills indexando tools avanzadas (CitationAuditor, LocalRAG,
    DeadlineGuard, AgenticCitator, PrecedentBoard).

    Cada tool avanzada de V2.2-B/C y V2.3-A se expone como skill pública
    descubrible, complementaria a los agentes del organigrama.
    """
    return [
        Skill(
            id="citation-auditor",
            name="Citation Auditor Skill",
            description=(
                "Pipeline fail-closed de citation audit pre-reveal (V2.2-B). "
                "Verifica cada cita contra el corpus ALBRA y bloquea phantom "
                "citations antes de mostrar el texto al usuario."
            ),
            category="review",
            practice_areas=list(_ALL_PRACTICE_AREAS),
            mcp_tool_name="audit_citation",
            input_schema={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
            output_type="dict",
            tags=["audit", "citation", "phantom", "fail-closed"],
            examples=[
                {
                    "input": {
                        "text": (
                            "El artículo 13 de la Constitución Política de 1991..."
                        )
                    },
                    "output": {
                        "revealed": True,
                        "verified_count": 1,
                        "phantom_count": 0,
                    },
                },
            ],
        ),
        Skill(
            id="local-rag",
            name="Local RAG Skill",
            description=(
                "RAG local ligero (TF-IDF + cosine) sobre el corpus ALBRA V1.1. "
                "Pure Python, sin dependencias externas (no OpenAI, no ChromaDB). "
                "Devuelve chunks relevantes con score."
            ),
            category="research",
            practice_areas=list(_ALL_PRACTICE_AREAS),
            mcp_tool_name="search_corpus",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "k": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
            output_type="list",
            tags=["search", "rag", "corpus", "tf-idf"],
            examples=[
                {
                    "input": {"query": "tutela salud", "k": 5},
                    "output": [
                        {"chunk_id": "const-1991-art-13", "score": 0.42}
                    ],
                },
            ],
        ),
        Skill(
            id="deadline-guard",
            name="Deadline Guard Skill",
            description=(
                "Verifica términos procesales colombianos de forma determinista "
                "(V2.2-C). Prescripción civil/laboral, contestación de demanda, "
                "recursos, impugnación, tutela. Devuelve ok/expired + días."
            ),
            category="deadline",
            practice_areas=list(_ALL_PRACTICE_AREAS),
            mcp_tool_name="verify_deadline",
            input_schema={
                "type": "object",
                "properties": {
                    "claim_date": {"type": "string"},
                    "event_date": {"type": "string"},
                    "deadline_type": {"type": "string"},
                },
                "required": ["claim_date", "event_date", "deadline_type"],
            },
            output_type="dict",
            tags=["deadline", "prescripcion", "procedural", "deterministic"],
            examples=[
                {
                    "input": {
                        "claim_date": "2020-01-01",
                        "event_date": "2024-01-01",
                        "deadline_type": "prescripcion_civil_extracontractual",
                    },
                    "output": {
                        "ok": False,
                        "expired": True,
                        "days_elapsed": 1461,
                    },
                },
            ],
        ),
        Skill(
            id="agentic-citator",
            name="Agentic Citator Skill",
            description=(
                "Citador agencial con treatment labels para jurisprudencia "
                "colombiana (V2.2-C). Clasifica cómo una sentencia cita a otra: "
                "followed, distinguished, doubted, overruled, per_incuriam, etc."
            ),
            category="analysis",
            practice_areas=list(_ALL_PRACTICE_AREAS),
            mcp_tool_name="analyze_treatment",
            input_schema={
                "type": "object",
                "properties": {
                    "citing_text": {"type": "string"},
                    "cited_decision_id": {"type": "string"},
                },
                "required": ["citing_text", "cited_decision_id"],
            },
            output_type="dict",
            tags=["citation", "treatment", "precedent", "jurisprudence"],
            examples=[
                {
                    "input": {
                        "citing_text": (
                            "La Corte sigue el criterio de C-251/2002..."
                        ),
                        "cited_decision_id": "C-251/2002",
                    },
                    "output": {"treatment": "followed", "confidence": 0.9},
                },
            ],
        ),
        Skill(
            id="precedent-board",
            name="Precedent Board Skill",
            description=(
                "Board de precedents con promoción tentative→confirmed (V2.3-A). "
                "Mantiene el corpus de citas válidas y descontesta phantom "
                "citations aprendidas de fallos anteriores."
            ),
            category="analysis",
            practice_areas=list(_ALL_PRACTICE_AREAS),
            mcp_tool_name="verify_audit_chain",
            input_schema={
                "type": "object",
                "properties": {"matter_id": {"type": "string"}},
                "required": ["matter_id"],
            },
            output_type="dict",
            tags=["precedent", "treatment", "board", "promotion"],
            examples=[
                {
                    "input": {"matter_id": "m-001"},
                    "output": {
                        "ok": True,
                        "total_precedents": 12,
                        "confirmed": 8,
                    },
                },
            ],
        ),
    ]


# =========================================================================
# SINGLETON (V2.5-A: lazy + resettable para tests)
# =========================================================================

_marketplace: SkillsMarketplace | None = None


def get_marketplace() -> SkillsMarketplace:
    """Devuelve el SkillsMarketplace singleton global (lazy init + bootstrap).

    En la primera llamada construye un SkillsMarketplace y lo guarda en el
    módulo. Llamadas subsiguientes devuelven la misma instancia (con las 15
    skills bootstrapped + las que se hayan registrado manualmente).

    Para tests: ``reset_marketplace()`` o ``monkeypatch.setattr(module,
    "_marketplace", None)`` resetean el singleton.
    """
    global _marketplace
    if _marketplace is None:
        _marketplace = SkillsMarketplace()
    return _marketplace


def reset_marketplace() -> None:
    """Resetea el singleton global (para tests)."""
    global _marketplace
    _marketplace = None
