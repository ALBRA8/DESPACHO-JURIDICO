"""
SOPs jurídicos - Standard Operating Procedures como handoffs tipados.

Inspirado en MetaGPT: cada SOP es un workflow contractual donde cada
paso emite artefactos tipados que el siguiente consume.

NO es código - es metadata. El workflow engine + handoffs lo consumen.

Ejemplo: SOP "Presentar Demanda Civil"
- Step 1: intake (cliente + hechos) → Output: HechosDTO
- Step 2: analisis_preliminar (HechosDTO) → Output: PreliminarDTO
- Step 3: redaccion_demanda (PreliminarDTO) → Output: DemandaDTO
- Step 4: revision_interna (DemandaDTO) → Output: DemandaRevisadaDTO
- Step 5: aprobacion_cliente (DemandaRevisadaDTO) → Output: AprobacionDTO
- Step 6: radicacion (AprobacionDTO) → Output: RadicacionDTO
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SOPStep:
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    requires_hitl: bool = False
    capability_required: str = ""
    estimated_minutes: int = 30


@dataclass
class LegalSOP:
    name: str
    description: str
    jurisdiction: str = "CO"
    steps: list[SOPStep] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "jurisdiction": self.jurisdiction,
            "steps": [
                {
                    "name": s.name,
                    "description": s.description,
                    "input_schema": s.input_schema,
                    "output_schema": s.output_schema,
                    "requires_hitl": s.requires_hitl,
                    "capability_required": s.capability_required,
                    "estimated_minutes": s.estimated_minutes,
                }
                for s in self.steps
            ],
        }


# --- SOPs predefinidos (vacíos - se cargan con conocimiento jurídico después) ---

DEMANDA_CIVIL_SOP = LegalSOP(
    name="demanda_civil",
    description="SOP para redacción y radicación de demanda civil en Colombia",
    jurisdiction="CO",
    steps=[
        SOPStep(
            name="intake_hechos",
            description="Recopilación de hechos con el cliente",
            input_schema={"cliente": "str", "canal": "str"},
            output_schema={"hechos": "list[str]", "petitorios": "list[str]", "pruebas": "list[str]"},
            capability_required="conversation",
            estimated_minutes=90,
        ),
        SOPStep(
            name="analisis_preliminar",
            description="Análisis jurídico preliminar de viabilidad",
            input_schema={"hechos": "list[str]"},
            output_schema={"viabilidad": "bool", "fundamentos": "list[str]", "riesgos": "list[str]"},
            capability_required="legal_research",
            estimated_minutes=120,
        ),
        SOPStep(
            name="redaccion_demanda",
            description="Redacción de la demanda con fundamentos de derecho",
            input_schema={"hechos": "list", "fundamentos": "list", "petitorios": "list"},
            output_schema={"documento": "str", "articulos_citados": "list[str]"},
            capability_required="document_generation",
            estimated_minutes=180,
        ),
        SOPStep(
            name="revision_interna",
            description="Revisión por abogado senior del despacho",
            input_schema={"documento": "str"},
            output_schema={"documento_revisado": "str", "observaciones": "list[str]"},
            capability_required="document_reading",
            estimated_minutes=60,
        ),
        SOPStep(
            name="aprobacion_cliente",
            description="Aprobación del cliente - HITL OBLIGATORIO",
            input_schema={"documento_revisado": "str"},
            output_schema={"aprobado": "bool", "comentarios_cliente": "list[str]"},
            requires_hitl=True,
            capability_required="external_communication",
            estimated_minutes=120,
        ),
        SOPStep(
            name="radicacion",
            description="Radicación ante juzgado competente",
            input_schema={"documento_revisado": "str", "aprobado": "bool"},
            output_schema={"radicado": "str", "juzgado": "str", "fecha": "str"},
            requires_hitl=True,
            capability_required="external_communication",
            estimated_minutes=60,
        ),
    ],
)


CONTESTACION_DEMANDA_SOP = LegalSOP(
    name="contestacion_demanda",
    description="SOP para contestar demanda civil",
    jurisdiction="CO",
    steps=[
        SOPStep(
            name="analisis_demanda_inicial",
            description="Lectura y análisis de la demanda inicial",
            input_schema={"documento": "str"},
            output_schema={"pretensiones": "list", "fundamentos_actor": "list", "pruebas_actor": "list"},
            capability_required="document_reading",
            estimated_minutes=120,
        ),
        SOPStep(
            name="identificacion_excepciones",
            description="Identificación de excepciones y defensas",
            input_schema={"pretensiones": "list", "fundamentos_actor": "list"},
            output_schema={"excepciones": "list", "defensas": "list", "fundamentos_propios": "list"},
            capability_required="legal_research",
            estimated_minutes=180,
        ),
        SOPStep(
            name="redaccion_contestacion",
            description="Redacción del escrito de contestación",
            input_schema={"excepciones": "list", "defensas": "list"},
            output_schema={"documento": "str", "articulos_citados": "list"},
            capability_required="document_generation",
            estimated_minutes=240,
        ),
        SOPStep(
            name="aprobacion_cliente",
            description="Aprobación del cliente - HITL OBLIGATORIO",
            input_schema={"documento": "str"},
            output_schema={"aprobado": "bool"},
            requires_hitl=True,
            capability_required="external_communication",
            estimated_minutes=120,
        ),
        SOPStep(
            name="radicacion_contestacion",
            description="Radicación dentro del término legal",
            input_schema={"documento": "str", "aprobado": "bool"},
            output_schema={"radicado": "str", "fecha": "str"},
            requires_hitl=True,
            capability_required="external_communication",
            estimated_minutes=60,
        ),
    ],
)


# Catálogo
SOP_CATALOG: dict[str, LegalSOP] = {
    "demanda_civil": DEMANDA_CIVIL_SOP,
    "contestacion_demanda": CONTESTACION_DEMANDA_SOP,
}


def get_sop(name: str) -> LegalSOP | None:
    return SOP_CATALOG.get(name)


def list_sops() -> list[dict[str, Any]]:
    return [
        {
            "name": s.name,
            "description": s.description,
            "jurisdiction": s.jurisdiction,
            "steps_count": len(s.steps),
            "hitl_steps": sum(1 for st in s.steps if st.requires_hitl),
            "estimated_total_minutes": sum(st.estimated_minutes for st in s.steps),
        }
        for s in SOP_CATALOG.values()
    ]
