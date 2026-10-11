"""
LEGAL SPECIALISTS ALBRA - placeholders arquitectónicos para futuros subagentes.

NO se construyen ahora - solo la interfaz para que luego puedan conectarse
al organismo base via HandoffProtocol.

Especialidades jurídicas futuras:
- civil
- penal
- laboral
- administrativo
- constitucional
- tributario
- propiedad intelectual
- proteccion de datos
- consumidor
- societario
- internacional
- litigios
- compliance
- familia
- sucesiones
- ambiental
- minero
- urbanistico
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SpecialistProfile:
    codename: str
    area: str  # civil | penal | laboral | ...
    description: str
    required_capabilities: list[str] = field(default_factory=list)
    required_knowledge: list[str] = field(default_factory=list)
    default_autonomy_ceiling: str = "L2_EXECUTE_SAFE"  # conservativo
    requires_hitl_for: tuple[str, ...] = ("external_communication", "document_generation")

    def as_dict(self) -> dict[str, Any]:
        return {
            "codename": self.codename,
            "area": self.area,
            "description": self.description,
            "required_capabilities": self.required_capabilities,
            "required_knowledge": self.required_knowledge,
            "default_autonomy_ceiling": self.default_autonomy_ceiling,
            "requires_hitl_for": list(self.requires_hitl_for),
        }


# Catálogo - VACÍO por diseño, solo perfiles declarados
SPECIALIST_CATALOG: dict[str, SpecialistProfile] = {
    "civil": SpecialistProfile(
        codename="ALBRA-CIVIL-V1",
        area="civil",
        description="Especialista en derecho civil (contratos, obligaciones, sucesiones, familia)",
        required_capabilities=["legal_research", "document_generation", "external_communication"],
        required_knowledge=["codigo_civil", "jurisprudencia_civil"],
    ),
    "penal": SpecialistProfile(
        codename="ALBRA-PENAL-V1",
        area="penal",
        description="Especialista en derecho penal (delitos, proceso penal, defensa técnica)",
        required_capabilities=["legal_research", "document_generation"],
        required_knowledge=["codigo_penal", "cpp", "jurisprudencia_penal"],
        default_autonomy_ceiling="L1_RECOMMEND",  # penal es delicado
    ),
    "laboral": SpecialistProfile(
        codename="ALBRA-LABORAL-V1",
        area="laboral",
        description="Especialista en derecho laboral (contratos de trabajo, despidos, demandas laborales)",
        required_capabilities=["legal_research", "document_generation", "external_communication"],
        required_knowledge=["codigo_sustantivo_trabajo", "jurisprudencia_laboral"],
    ),
    "administrativo": SpecialistProfile(
        codename="ALBRA-ADMIN-V1",
        area="administrativo",
        description="Especialista en derecho administrativo (actos administrativos, nulidad, contratos estatales)",
        required_capabilities=["legal_research", "document_generation"],
        required_knowledge=["cca", "jurisprudencia_administrativa"],
    ),
    "constitucional": SpecialistProfile(
        codename="ALBRA-CONST-V1",
        area="constitucional",
        description="Especialista en derecho constitucional (tutela, constitución, derechos fundamentales)",
        required_capabilities=["legal_research", "document_generation"],
        required_knowledge=["constitucion", "jurisprudencia_constitucional"],
    ),
    "tributario": SpecialistProfile(
        codename="ALBRA-TRIB-V1",
        area="tributario",
        description="Especialista en derecho tributario (impuestos, DIAN, fiscalidad)",
        required_capabilities=["legal_research"],
        required_knowledge=["estatuto_tributario", "jurisprudencia_tributaria"],
    ),
    "propiedad_intelectual": SpecialistProfile(
        codename="ALBRA-PI-V1",
        area="propiedad_intelectual",
        description="Especialista en P.I. (marcas, patentes, derechos de autor, INVITES)",
        required_capabilities=["legal_research", "document_generation"],
        required_knowledge=["decision_48_andino", "ley_599_pi", "ley_1403"],
    ),
    "proteccion_datos": SpecialistProfile(
        codename="ALBRA-HABEAS-V1",
        area="proteccion_datos",
        description="Especialista en protección de datos (Ley 1581, habeas data, SIC)",
        required_capabilities=["legal_research"],
        required_knowledge=["ley_1581", "decreto_1377"],
    ),
    "consumidor": SpecialistProfile(
        codename="ALBRA-CONSUM-V1",
        area="consumidor",
        description="Especialista en derecho del consumidor (Estatuto del Consumidor, SIC)",
        required_capabilities=["legal_research"],
        required_knowledge=["ley_1480", "jurisprudencia_consumidor"],
    ),
    "societario": SpecialistProfile(
        codename="ALBRA-SOC-V1",
        area="societario",
        description="Especialista en derecho societario (sociedades, Supersociedades, asambleas)",
        required_capabilities=["legal_research", "document_generation"],
        required_knowledge=["codigo_comercio", "ley_1258"],
    ),
    "internacional": SpecialistProfile(
        codename="ALBRA-INT-V1",
        area="internacional",
        description="Especialista en derecho internacional (tratados, conflictos de leyes)",
        required_capabilities=["legal_research"],
        required_knowledge=["tratados_internacionales", "ley_153_reglas_private"],
    ),
    "litigios": SpecialistProfile(
        codename="ALBRA-LIT-V1",
        area="litigios",
        description="Especialista en litigios (estrategia procesal, audiencias, recursos)",
        required_capabilities=["legal_research", "document_generation", "external_communication"],
        required_knowledge=["cpc", "cgp"],
        default_autonomy_ceiling="L1_RECOMMEND",
    ),
    "compliance": SpecialistProfile(
        codename="ALBRA-COMP-V1",
        area="compliance",
        description="Especialista en compliance (SAGRILAFT, prevención de lavado, due diligence)",
        required_capabilities=["legal_research"],
        required_knowledge=["ley_1778", "resolucion_012_sfc"],
    ),
    "familia": SpecialistProfile(
        codename="ALBRA-FAM-V1",
        area="familia",
        description="Especialista en derecho de familia (divorcios, custodia, alimentos)",
        required_capabilities=["legal_research", "document_generation"],
        required_knowledge=["ley_1098", "codigo_civil_familia"],
    ),
    "sucesiones": SpecialistProfile(
        codename="ALBRA-SUC-V1",
        area="sucesiones",
        description="Especialista en sucesiones (herencias, testamentos, particiones)",
        required_capabilities=["legal_research", "document_generation"],
        required_knowledge=["codigo_civil_sucesiones"],
    ),
}


def get_specialist(area: str) -> SpecialistProfile | None:
    return SPECIALIST_CATALOG.get(area.lower())


def list_specialists() -> list[dict[str, Any]]:
    return [s.as_dict() for s in SPECIALIST_CATALOG.values()]


def is_specialist_ready(area: str) -> bool:
    """Por ahora NINGÚN especialista está 'ready' - solo el perfil está declarado."""
    return False
