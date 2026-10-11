"""
COLOMBIA LEGAL KNOWLEDGE SCHEMAS V1.0.

Modelos de conocimiento jurídico colombiano.
Separación estricta entre:
- RAW SOURCE (URL/documento original)
- DOCUMENT (parseado, con metadata)
- NORM (ley, decreto, código, etc.)
- ARTICLE (disposición específica dentro de norma)
- PROVISION (texto concreto)
- JURISPRUDENCE (sentencia)
- DOCTRINE (libro/artículo académico)
- EMBEDDINGS (vector - solo recuperación, NO fuente de verdad)
- EVIDENCE (resultado trazable)

NO se inventa conocimiento jurídico. Los modelos son vacíos hasta
que se cargue contenido verificado en FASE posterior.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from enum import IntEnum
from typing import Any

# ============================================================
# TIPOS DE DOCUMENTO JURÍDICO COLOMBIANO
# ============================================================

class DocumentType(str):
    """Tipos documentales para Colombia."""


DOCUMENT_TYPES: tuple[str, ...] = (
    "constitucion",
    "acto_legislativo",
    "reforma_constitucional",
    "ley",
    "decreto_ley",
    "decreto_reglamentario",
    "decreto",
    "resolucion",
    "circular",
    "acuerdo",
    "reglamento",
    "codigo",
    "estatuto",
    "ordenanza",
    "normativa_territorial",
    # Jurisprudencia
    "sentencia",
    "auto",
    "providencia",
    # Doctrina
    "libro_doctrina",
    "articulo_academico",
    "tratado",
    # Otros
    "concepto",
    "circulare_externa",
)


# ============================================================
# JERARQUÍA DE FUENTES (S0-S4)
# ============================================================

class SourceTier(IntEnum):
    """Jerarquía de confianza de fuentes."""
    S0_PRIMARY_SUPERIOR = 0   # Constitución, leyes, decretos, jurisprudencia oficial
    S1_OFFICIAL = 1            # SUIN-Juriscol, Congreso, Cortes, Consejo de Estado
    S2_ACADEMIC = 2            # Universidades, Biblioteca Luis Ángel Arango, Banrep
    S3_DOCTRINE = 3            # Tratados, libros doctrinales
    S4_SECONDARY = 4           # Fuentes secundarias - solo contexto/descubrimiento


TIER_LABELS: dict[SourceTier, str] = {
    SourceTier.S0_PRIMARY_SUPERIOR: "Fuente primaria superior",
    SourceTier.S1_OFFICIAL: "Fuente jurídica oficial",
    SourceTier.S2_ACADEMIC: "Fuente académica",
    SourceTier.S3_DOCTRINE: "Doctrina especializada",
    SourceTier.S4_SECONDARY: "Fuente secundaria",
}


# ============================================================
# AUTORIDADES COLOMBIANAS
# ============================================================

COLOMBIA_AUTHORITIES: tuple[str, ...] = (
    # Poder Legislativo
    "Congreso de la República",
    # Poder Ejecutivo
    "Presidencia de la República",
    "Ministerio del Interior",
    "Ministerio de Justicia",
    "Ministerio de Hacienda",
    "Ministerio de Defensa",
    "Ministerio de Salud",
    "Ministerio de Educación",
    "Ministerio de Trabajo",
    "Ministerio de Ambiente",
    "Ministerio de Tecnologías",
    # Rama Judicial
    "Corte Constitucional",
    "Corte Suprema de Justicia",
    "Consejo de Estado",
    "Consejo Superior de la Judicatura",
    "Tribunal Superior",
    "Juzgado",
    # Entidades
    "DIAN",
    "Superintendencia de Sociedades",
    "Superintendencia Financiera",
    "Superintendencia de Industria y Comercio",
    "Superintendencia de Salud",
    "Procuraduría General",
    "Defensoría del Pueblo",
    "Fiscalía General",
    "Contraloría General",
    "Registraduría Nacional",
    # Otros
    "Banco de la República",
    "ANLA",
    "INVÍAS",
    "Departamento Nacional de Planeación",
    # Territorial
    "Asamblea Departamental",
    "Concejo Municipal",
    "Alcaldía",
    "Gobernación",
)


# ============================================================
# ESTADO DE VIGENCIA
# ============================================================

VALIDITY_STATUS: tuple[str, ...] = (
    "vigente",          # currently in force
    "derogada",         # repealed explicitly
    "modificada",       # amended (parts still in force)
    "sustituida",       # replaced by another norm
    "suspendida",       # temporarily suspended
    "inexequible",      # declared unconstitutional (removed from order)
    "nula",             # void
    "perdida_vigencia", # lost validity (e.g. temporary norms)
    "historica",        # historical version - not current
    "pendiente",        # not yet in force
)


# ============================================================
# SCHEMA: NORM (ley, decreto, código, etc.)
# ============================================================

@dataclass
class Norm:
    """Norma jurídica colombiana.

    NO contiene texto de artículos - solo metadata y referencia
    a la colección de artículos (Articles).
    """
    id: str                          # internal ID
    document_type: str               # DOCUMENT_TYPES
    authority: str                   # COLOMBIA_AUTHORITIES
    jurisdiction: str = "CO"        # ISO code
    number: str = ""                 # "Ley 100 de 1993"
    title: str = ""
    source_url: str = ""             # URL oficial
    source_tier: SourceTier = SourceTier.S1_OFFICIAL

    # Temporal
    date_issued: date | None = None        # expedición
    publication_date: date | None = None    # publicación Diario Oficial
    effective_from: date | None = None      # entrada en vigor
    effective_until: date | None = None    # fin de vigencia (None=vigente)
    status: str = "vigente"

    # Versioning
    version: int = 1
    supersedes_id: str | None = None       # ID de la versión anterior
    superseded_by_id: str | None = None     # ID de la versión que la sustituye

    # Relationships
    parent_document_id: str | None = None
    related_norm_ids: list[str] = field(default_factory=list)
    modifying_norm_ids: list[str] = field(default_factory=list)  # normas que la modifican
    modified_by_norm_ids: list[str] = field(default_factory=list)  # normas modificadas por ella

    # Metadata
    subject: str = ""                 # materia: civil, penal, laboral, etc.
    matter: str = ""                  # materia específica
    official_source: bool = True
    content_hash: str = ""            # SHA-256 del contenido original
    retrieval_timestamp: float = 0.0
    provenance: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    # Article IDs
    article_ids: list[str] = field(default_factory=list)

    def is_active_at(self, when: date) -> bool:
        """Verifica si la norma estaba vigente en una fecha dada."""
        if self.effective_from and when < self.effective_from:
            return False
        if self.effective_until and when > self.effective_until:
            return False
        if self.status in ("derogada", "sustituida", "inexequible", "nula", "perdida_vigencia"):
            # Si el status es de pérdida - hay que mirar effective_until
            return False
        return True

    def is_current(self) -> bool:
        """¿Está vigente hoy?"""
        return self.is_active_at(date.today())


# ============================================================
# SCHEMA: ARTICLE (disposición específica dentro de norma)
# ============================================================

@dataclass
class Article:
    """Artículo específico dentro de una norma.

    Ej: Artículo 25 del Código Civil colombiano.
    """
    id: str
    norm_id: str                  # Norma a la que pertenece
    article_number: str           # "25", "200", "350-A"
    section: str = ""             # capítulo, título, libro
    text: str = ""                # texto literal del artículo
    epigraph: str = ""            # título corto del artículo
    status: str = "vigente"

    # Temporal del artículo (puede ser derogado independientemente)
    effective_from: date | None = None
    effective_until: date | None = None
    modified_by_article_ids: list[str] = field(default_factory=list)
    modifying_article_ids: list[str] = field(default_factory=list)

    # Embedding (separada del texto)
    embedding: list[float] = field(default_factory=list)
    embedding_model: str = ""
    content_hash: str = ""

    metadata: dict[str, Any] = field(default_factory=dict)

    def is_active_at(self, when: date) -> bool:
        if self.effective_from and when < self.effective_from:
            return False
        if self.effective_until and when > self.effective_until:
            return False
        if self.status in ("derogada", "sustituida", "inexequible"):
            return False
        return True


# ============================================================
# VOCABULARIO CONTROLADO DE EFECTOS JURISPRUDENCIALES — B1 HARDENING
# ============================================================

# B1: Separar REACH (alcance) de FORCE (fuerza precedencial)
# Estas son dimensiones jurídicas distintas:
# - REACH: a quién afecta la decisión (erga_omnes vs inter_partes)
# - FORCE: cómo se trata como precedente (vinculante vs orientador)

# --- REACH / ALCANCE ---
REACH_VALUES: frozenset[str] = frozenset({
    "inter_partes",     # afecta solo a las partes del proceso
    "erga_omnes",      # afecta a todos (constitucionalidad, unificación)
    "unknown",         # no se puede determinar
})

def validate_reach(reach: str | None) -> str:
    """Valida y normaliza reach. Si inválido → 'unknown' (no asumir inter_partes)."""
    if not reach:
        return "unknown"
    r = reach.lower().strip()
    return r if r in REACH_VALUES else "unknown"

# --- FORCE / FUERZA PRECEDENCIAL ---
FORCE_VALUES: frozenset[str] = frozenset({
    "vinculante",              # precedente vinculante (Corte Constitucional AT/IN/EX)
    "precedente",              # regla establecida como precedente
    "criterio_interpretativo", # guía interpretativa no vinculante
    "orientador",             # criterio orientador (no vinculante)
    "hito_jurisprudencial",   # hito de impacto doctrinal
    "desconocido",            # fuerza no determinable
})

def validate_force(force: str | None) -> str:
    """Valida y normaliza force. Si inválido → 'desconocido'."""
    if not force:
        return "desconocido"
    f = force.lower().strip()
    return f if f in FORCE_VALUES else "desconocido"

# Fuerzas que implican vinculancia
BINDING_FORCES: frozenset[str] = frozenset({
    "vinculante", "precedente",
})

def is_binding_force(force: str | None) -> bool:
    """Determina si una fuerza implica vinculancia."""
    return validate_force(force) in BINDING_FORCES

# --- DEPRECATED: effect vocabulario (compat hacia atrás) ---
EFFECT_VALUES: frozenset[str] = frozenset({
    "inter_partes", "erga_omnes", "precedente", "criterio_interpretativo",
    "vinculante", "orientador", "hito_jurisprudencial", "desconocido",
})

BINDING_EFFECTS: frozenset[str] = frozenset({
    "erga_omnes", "precedente", "vinculante",
})

NON_BINDING_EFFECTS: frozenset[str] = frozenset({
    "inter_partes", "criterio_interpretativo", "orientador", "hito_jurisprudencial",
    "desconocido",
})

def validate_effect(effect: str | None) -> str:
    """DEPRECATED: usar validate_reach + validate_force.
    Compat: si effect contiene un valor de reach, lo deja en reach.
    Si contiene un valor de force, lo deja en force.
    """
    if not effect:
        return "desconocido"
    e = effect.lower().strip()
    return e if e in EFFECT_VALUES else "desconocido"

def is_binding_effect(effect: str | None) -> bool:
    """DEPRECATED: usar is_binding_force."""
    return validate_effect(effect) in BINDING_EFFECTS


# ============================================================
# SCHEMA: JURISPRUDENCE (sentencia)
# ============================================================

@dataclass
class Jurisprudence:
    """Sentencia o providencia judicial.

    P1-1 (CIERRE): NO usar binding:bool binario. Diferenciar efectos jurídicos.
    """
    id: str
    court: str                     # "Corte Constitucional", "Corte Suprema", "Consejo de Estado"
    process_type: str = ""         # "Sentencia C", "Sentencia STC", etc.
    file_number: str = ""          # expediente "T-123/2023"
    decision_date: date | None = None

    # B1 HARDENING: reach y force separados
    # REACH: a quién afecta la decisión
    reach: str = "unknown"  # B1: default 'unknown' (NO asumir inter_partes)
    # FORCE: cómo se trata como precedente
    force: str = "desconocido"  # B1: default 'desconocido'

    # DEPRECATED: effect — compat hacia atrás.
    # Si se pasa effect= al constructor, se deriva reach+force de él.
    # Si no se pasa, reach='unknown' y force='desconocido'.
    effect: str = ""  # B1: vacío por defecto, se procesa en __post_init__

    # B1: validar reach, force, y derivar effect en __post_init__
    def __post_init__(self) -> None:
        # Validar reach y force con vocabulario controlado
        self.reach = validate_reach(self.reach)
        self.force = validate_force(self.force)
        # Compat: si effect fue pasado, migrar a reach/force
        if self.effect:
            eff = self.effect.lower().strip()
            # Si effect es un valor de reach, usarlo como reach
            if eff in REACH_VALUES:
                if self.reach == "unknown":
                    self.reach = eff
            # Si effect es un valor de force, usarlo como force
            if eff in FORCE_VALUES:
                if self.force == "desconocido":
                    self.force = eff
            # Si effect es un valor del vocabulario antiguo que mezcla ambos:
            if eff == "erga_omnes":
                self.reach = "erga_omnes"
                self.force = "vinculante" if self.force == "desconocido" else self.force
            elif eff == "inter_partes":
                self.reach = "inter_partes"
            elif eff == "vinculante":
                self.force = "vinculante"
            elif eff == "precedente":
                self.force = "precedente"
            elif eff == "orientador":
                self.force = "orientador"
            elif eff == "criterio_interpretativo":
                self.force = "criterio_interpretativo"
            elif eff == "hito_jurisprudencial":
                self.force = "hito_jurisprudencial"
            elif eff == "desconocido":
                pass  # keep defaults
            self.effect = ""  # limpiar para evitar uso futuro

    # Compat: binding deriva de force (no de reach)
    @property
    def binding(self) -> bool:
        """B1: binding deriva de FORCE, no de reach."""
        return is_binding_force(self.force)

    # Compat: effect_property deriva reach+force
    @property
    def effect_resolved(self) -> str:
        """B1: devuelve effect combinado para compat."""
        if self.reach != "unknown" and self.force != "desconocido":
            return f"{self.reach}+{self.force}"
        return self.force if self.force != "desconocido" else self.reach

    # Jurisdicción (P1-3 FIX: necesario para filtrar sentencias de otros países)
    jurisdiction: str = "CO"

    # Contenido jurídico
    ponente: str = ""              # magistrado ponente
    facts: str = ""                # hechos relevantes
    legal_issue: str = ""         # problema jurídico
    decision: str = ""            # decisión final
    ratio_decidendi: str = ""      # razón principal de la decisión
    obiter_dicta: str = ""        # consideraciones no vinculantes
    holding: str = ""             # regla establecida como precedente

    # Relaciones
    cites_jurisprudence_ids: list[str] = field(default_factory=list)
    cited_by_ids: list[str] = field(default_factory=list)
    reversed_by_id: str | None = None
    reaffirms_id: str | None = None
    distinguishes_id: str | None = None

    # Vigencia del precedente
    precedent_status: str = "vigente"   # vigente, superado, derogado

    # Metadata
    source_url: str = ""
    source_tier: SourceTier = SourceTier.S0_PRIMARY_SUPERIOR
    authority: str = ""  # court name
    official_source: bool = True
    content_hash: str = ""
    retrieval_timestamp: float = 0.0
    provenance: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    # Embedding
    embedding: list[float] = field(default_factory=list)
    embedding_model: str = ""


# ============================================================
# SCHEMA: DOCTRINE (libro/artículo académico)
# ============================================================

@dataclass
class Doctrine:
    """Doctrina jurídica (libro, tratado, artículo académico)."""
    id: str
    author: str = ""
    title: str = ""
    publication_year: int | None = None
    publisher: str = ""

    # Tipo
    doctrine_type: str = "articulo"  # articulo | libro | tratado | comentario

    # Contenido
    abstract: str = ""
    text: str = ""
    cites_norm_ids: list[str] = field(default_factory=list)
    cites_jurisprudence_ids: list[str] = field(default_factory=list)

    # Metadata
    source_url: str = ""
    source_tier: SourceTier = SourceTier.S3_DOCTRINE
    authority: str = ""  # universidad, editorial, etc.
    content_hash: str = ""
    retrieval_timestamp: float = 0.0
    provenance: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    # Embedding
    embedding: list[float] = field(default_factory=list)
    embedding_model: str = ""


# ============================================================
# SCHEMA: LegalDocument (genérico para ingestion)
# ============================================================

@dataclass
class LegalDocument:
    """Documento jurídico genérico - se convierte en Norm/Article/etc.

    Usado por el pipeline de ingestión antes de clasificar.
    """
    source_id: str                # ID único de la fuente
    document_id: str              # ID interno
    document_type: str            # DOCUMENT_TYPES
    authority: str
    jurisdiction: str = "CO"
    title: str = ""
    number: str = ""

    # Temporal
    date_issued: date | None = None
    publication_date: date | None = None
    effective_from: date | None = None
    effective_until: date | None = None
    status: str = "vigente"

    # Contenido
    raw_content: bytes = b""
    parsed_text: str = ""
    content_hash: str = ""

    # Metadata
    source_url: str = ""
    source_tier: SourceTier = SourceTier.S1_OFFICIAL
    official_source: bool = True
    retrieval_timestamp: float = 0.0
    parent_document_id: str | None = None
    related_documents: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def compute_hash(self) -> str:
        """Calcula SHA-256 del contenido para trazabilidad."""
        if not self.content_hash:
            self.content_hash = hashlib.sha256(self.raw_content).hexdigest()
        return self.content_hash

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "document_id": self.document_id,
            "document_type": self.document_type,
            "authority": self.authority,
            "jurisdiction": self.jurisdiction,
            "title": self.title,
            "number": self.number,
            "status": self.status,
            "source_tier": self.source_tier.name,
            "content_hash": self.compute_hash(),
        }


# ============================================================
# SCHEMA: EvidenceCandidate (resultado de retrieval)
# ============================================================

@dataclass
class EvidenceCandidate:
    """Candidato a evidencia tras retrieval.

    Aún no es EvidenceChain item - necesita verificación.
    """
    source_id: str               # ID de la fuente (norma, sentencia, etc.)
    document_id: str
    source_tier: SourceTier
    authority: str
    document_type: str
    snippet: str                 # extracto relevante
    citation: str = ""           # cita formal (ej: "Ley 100 de 1993, art. 25")
    score: float = 0.0           # score de relevancia
    is_current: bool = True      # si está vigente
    retrieved_at: float = 0.0
    provenance: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "document_id": self.document_id,
            "source_tier": self.source_tier.name,
            "authority": self.authority,
            "document_type": self.document_type,
            "snippet": self.snippet,
            "citation": self.citation,
            "score": self.score,
            "is_current": self.is_current,
        }
