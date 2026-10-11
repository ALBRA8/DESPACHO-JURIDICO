"""
JERARQUÍA DE FUENTES JURÍDICAS COLOMBIANAS - V1.0.

S0 - FUENTE PRIMARIA SUPERIOR
    Constitución, leyes, actos legislativos, decretos,
    jurisprudencia oficial, Diario Oficial, fuentes oficiales.

S1 - FUENTES JURÍDICAS OFICIALES
    SUIN-Juriscol, Congreso, Corte Constitucional, Corte Suprema,
    Consejo de Estado, entidades oficiales, repositorios oficiales.

S2 - FUENTES ACADÉMICAS
    Universidades, bibliotecas jurídicas, repositorios académicos,
    centros de investigación, Biblioteca Luis Ángel Arango, Banrep.

S3 - DOCTRINA ESPECIALIZADA
    Libros, tratados, artículos, investigaciones, doctrina reconocida.

S4 - FUENTES SECUNDARIAS
    Solo contexto o descubrimiento. Nunca se elevan a primaria automáticamente.
"""
from __future__ import annotations

from dataclasses import dataclass

from albra.knowledge.schemas import TIER_LABELS, SourceTier


# Catálogo oficial de fuentes colombianas
@dataclass
class OfficialSource:
    id: str
    name: str
    url: str
    tier: SourceTier
    authority: str
    description: str = ""
    enabled: bool = True  # si está disponible para consulta
    requires_auth: bool = False


# Registry de fuentes oficiales colombianas (vacías - sin URL real)
# NO inventamos URLs - cuando exista una integración real, se agrega aquí.
COLOMBIA_OFFICIAL_SOURCES: dict[str, OfficialSource] = {
    # S0 - Primaria superior
    "diario_oficial": OfficialSource(
        id="diario_oficial",
        name="Diario Oficial",
        url="",  # pendiente de integración real
        tier=SourceTier.S0_PRIMARY_SUPERIOR,
        authority="Presidencia de la República",
        description="Publicación oficial de normas jurídicas",
    ),
    "constitucion_1991": OfficialSource(
        id="constitucion_1991",
        name="Constitución Política de Colombia 1991",
        url="",
        tier=SourceTier.S0_PRIMARY_SUPERIOR,
        authority="Asamblea Nacional Constituyente",
        description="Constitución Política vigente",
    ),
    # S1 - Oficiales
    "suin_juriscol": OfficialSource(
        id="suin_juriscol",
        name="SUIN-Juriscol",
        url="",
        tier=SourceTier.S1_OFFICIAL,
        authority="Banco de la República",
        description="Sistema Único de Información Normativa - Juriscol",
    ),
    "congreso": OfficialSource(
        id="congreso",
        name="Congreso de la República",
        url="",
        tier=SourceTier.S1_OFFICIAL,
        authority="Congreso de la República",
        description="Leyes, actos legislativos, proyectos de ley",
    ),
    "corte_constitucional": OfficialSource(
        id="corte_constitucional",
        name="Corte Constitucional",
        url="",
        tier=SourceTier.S1_OFFICIAL,
        authority="Corte Constitucional",
        description="Sentencias de constitucionalidad, tutela, revisión",
    ),
    "corte_suprema": OfficialSource(
        id="corte_suprema",
        name="Corte Suprema de Justicia",
        url="",
        tier=SourceTier.S1_OFFICIAL,
        authority="Corte Suprema de Justicia",
        description="Casación civil, penal, laboral",
    ),
    "consejo_estado": OfficialSource(
        id="consejo_estado",
        name="Consejo de Estado",
        url="",
        tier=SourceTier.S1_OFFICIAL,
        authority="Consejo de Estado",
        description="Justicia contencioso-administrativa",
    ),
    "alcaldia_bogota": OfficialSource(
        id="alcaldia_bogota",
        name="Alcaldía de Bogotá",
        url="",
        tier=SourceTier.S1_OFFICIAL,
        authority="Alcaldía de Bogotá",
        description="Decretos, acuerdos distritales",
    ),
    # S2 - Académicas
    "biblioteca_banrep": OfficialSource(
        id="biblioteca_banrep",
        name="Biblioteca Luis Ángel Arango",
        url="",
        tier=SourceTier.S2_ACADEMIC,
        authority="Banco de la República",
        description="Repositorio académico de obras jurídicas",
    ),
    "universidad_nacional": OfficialSource(
        id="universidad_nacional",
        name="Universidad Nacional - Biblioteca",
        url="",
        tier=SourceTier.S2_ACADEMIC,
        authority="Universidad Nacional",
        description="Repositorio académico",
    ),
    # S3 - Doctrina
    "editorial_temis": OfficialSource(
        id="editorial_temis",
        name="Editorial Temis",
        url="",
        tier=SourceTier.S3_DOCTRINE,
        authority="Editorial Temis",
        description="Libros doctrinales reconocidos",
    ),
    # S4 - Secundarias
    "redEscar": OfficialSource(
        id="redEscar",
        name="Red Iberoamericana de Estudios Jurídicos",
        url="",
        tier=SourceTier.S4_SECONDARY,
        authority="Red académica",
        description="Solo contexto/descubrimiento",
    ),
}


def get_source(source_id: str) -> OfficialSource | None:
    return COLOMBIA_OFFICIAL_SOURCES.get(source_id)


def list_sources_by_tier(tier: SourceTier) -> list[OfficialSource]:
    return [s for s in COLOMBIA_OFFICIAL_SOURCES.values() if s.tier == tier and s.enabled]


def can_back_compliance(tier: SourceTier) -> bool:
    """Solo S0 (primaria superior) y S1 (oficial) pueden respaldar cumplimiento definitivo."""
    return tier in (SourceTier.S0_PRIMARY_SUPERIOR, SourceTier.S1_OFFICIAL)


def tier_label(tier: SourceTier) -> str:
    return TIER_LABELS.get(tier, "Desconocida")


def authority_for_source(source_id: str) -> str:
    s = get_source(source_id)
    return s.authority if s else ""


def compare_tier(t1: SourceTier, t2: SourceTier) -> int:
    """Returns -1 if t1 more authoritative, 1 if t2 more, 0 if equal."""
    if t1 < t2:
        return -1
    if t1 > t2:
        return 1
    return 0
