"""
DATA CLASSIFICATION ALBRA - 8 niveles de sensibilidad.

Inspirado en CRM-ALBRA/src/lib/rbac.ts y prompt maestro §11.

Niveles (de menos a más sensible):
1. PUBLICO        - información públicamente divulgable
2. INTERNO        - uso interno del despacho
3. CONFIDENCIAL   - acceso restringido
4. DATO_PERSONAL  - PII - Ley 1581 de 2012 (Colombia)
5. DATO_SENSIBLE  - salud, biométricos, vida sexual - Ley 1581
6. SECRETO_PROFESIONAL - protegido por secreto de abogado
7. EXPEDIENTE_JURIDICO - caso concreto, máximo cuidado
8. CREDENCIAL     - tokens, contraseñas, API keys
9. SECRETO_TECNICO - know-how, algoritmos, config secreta

Reglas:
- Cada dato que entra al agente se clasifica
- La clasificación determina: almacenamiento, provider, retention, audit
- Datos sensibles → provider LOCAL siempre
- Credenciales → nunca se loguean, nunca van a memoria conversacional
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any


class DataClassification(IntEnum):
    PUBLICO = 1
    INTERNO = 2
    CONFIDENCIAL = 3
    DATO_PERSONAL = 4
    DATO_SENSIBLE = 5
    SECRETO_PROFESIONAL = 6
    EXPEDIENTE_JURIDICO = 7
    CREDENCIAL = 8
    SECRETO_TECNICO = 9


CLASSIFICATION_LABELS: dict[DataClassification, str] = {
    DataClassification.PUBLICO: "Público",
    DataClassification.INTERNO: "Interno",
    DataClassification.CONFIDENCIAL: "Confidencial",
    DataClassification.DATO_PERSONAL: "Dato personal",
    DataClassification.DATO_SENSIBLE: "Dato sensible",
    DataClassification.SECRETO_PROFESIONAL: "Secreto profesional",
    DataClassification.EXPEDIENTE_JURIDICO: "Expediente jurídico",
    DataClassification.CREDENCIAL: "Credencial",
    DataClassification.SECRETO_TECNICO: "Secreto técnico",
}


# Patrones de detección (regex/heurística)
CLASSIFICATION_PATTERNS: dict[DataClassification, list[str]] = {
    DataClassification.CREDENCIAL: [
        "password", "passwd", "contraseña", "token=", "api_key=",
        "apikey=", "client_secret", "bearer ", "private_key",
        "secret=", "authorization:",
    ],
    DataClassification.SECRETO_PROFESIONAL: [
        "expediente", "cliente", "abogado", "caso", "demanda",
        "secreto profesional", "confidencialidad abogado",
    ],
    DataClassification.EXPEDIENTE_JURIDICO: [
        "radicado", "juzgado", "proceso", "demandado", "demandante",
        "actor", "accionado", "proceso número", "expediente núm",
    ],
    DataClassification.DATO_SENSIBLE: [
        "salud", "enfermedad", "diabetes", "cáncer", "cancer", "vih",
        "discapacidad", "biométr", "biometric",
        "huella", "iris", "vida sexual", "orientación sexual",
        "política", "religión", "sindical",
    ],
    DataClassification.DATO_PERSONAL: [
        "cédula", "cedula", "dni", "ruc", "número de identificación",
        "fecha de nacimiento", "dirección", "teléfono", "email", "@",
        "nombre completo", "apellido",
    ],
    DataClassification.CONFIDENCIAL: [
        "confidencial", "privado", "no divulgar", "uso restringido",
    ],
    DataClassification.SECRETO_TECNICO: [
        "algoritmo", "know-how", "know how", "source code", "código fuente",
        "configuración técnica", "infraestructura",
    ],
}


def classify_data(text: str) -> DataClassification:
    """Clasifica un texto según patrones - devuelve el nivel MÁS ALTO detectado."""
    text_l = text.lower()
    detected: list[DataClassification] = []
    for classification, patterns in CLASSIFICATION_PATTERNS.items():
        for p in patterns:
            if p in text_l:
                detected.append(classification)
                break
    if not detected:
        return DataClassification.PUBLICO
    return max(detected)  # el más alto gana


def requires_local_provider(classification: DataClassification) -> bool:
    """Datos sensibles SIEMPRE van a modelo local."""
    return classification >= DataClassification.DATO_PERSONAL


def requires_hitl_to_share(classification: DataClassification) -> bool:
    """Compartir fuera del despacho requiere HITL."""
    return classification >= DataClassification.CONFIDENCIAL


def requires_encryption_at_rest(classification: DataClassification) -> bool:
    """Datos sensibles se encriptan al guardar."""
    return classification >= DataClassification.DATO_PERSONAL


def label(classification: DataClassification) -> str:
    return CLASSIFICATION_LABELS.get(classification, "Desconocido")


@dataclass
class ClassificationResult:
    classification: DataClassification
    label: str
    requires_local: bool
    requires_hitl_share: bool
    requires_encryption: bool
    matches: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "classification": self.classification.name,
            "label": self.label,
            "requires_local_provider": self.requires_local,
            "requires_hitl_to_share": self.requires_hitl_share,
            "requires_encryption_at_rest": self.requires_encryption,
            "matches": self.matches,
        }


def classify(text: str) -> ClassificationResult:
    """Clasificación completa con metadata."""
    text_l = text.lower()
    matches: list[str] = []
    detected: list[DataClassification] = []
    for c, patterns in CLASSIFICATION_PATTERNS.items():
        for p in patterns:
            if p in text_l:
                if c not in detected:
                    detected.append(c)
                matches.append(f"{c.name}:{p}")
                break
    if not detected:
        c = DataClassification.PUBLICO
    else:
        c = max(detected)
    return ClassificationResult(
        classification=c,
        label=label(c),
        requires_local=requires_local_provider(c),
        requires_hitl_share=requires_hitl_to_share(c),
        requires_encryption=requires_encryption_at_rest(c),
        matches=matches,
    )
