"""
LEGAL GATE ALBRA - clasifica acciones jurídicas en 5 estados.

Inspirado en RADAR-SECOP2/src/lib/evidence.ts (TruthLevels) y
prompt maestro §25.

Estados:
- APPROVED              → acción permitida sin restricciones
- APPROVED_WITH_LIMITS → permitida con condiciones
- REVIEW_REQUIRED       → requiere revisión humana
- BLOCKED               → prohibida
- UNKNOWN               → sin suficiente información

Acciones evaluadas:
- publicación de contenido
- firma/aceptación de contratos
- propiedad intelectual
- datos personales
- comunicaciones externas
- publicidad
- ventas
- contenido de terceros
- acciones jurídicas
- documentos legales
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from albra.observability.logger import get_logger
from albra.security.classification import DataClassification, classify


@dataclass
class LegalGateVerdict:
    verdict: str  # APPROVED | APPROVED_WITH_LIMITS | REVIEW_REQUIRED | BLOCKED | UNKNOWN
    action: str
    reason: str
    limits: list[str] = field(default_factory=list)
    required_reviewers: list[str] = field(default_factory=list)
    evidence_required: bool = False
    classification: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "action": self.action,
            "reason": self.reason,
            "limits": self.limits,
            "required_reviewers": self.required_reviewers,
            "evidence_required": self.evidence_required,
            "classification": self.classification,
        }


# Reglas del Legal Gate
LEGAL_RULES: dict[str, dict[str, Any]] = {
    "publish_content": {
        "default": "REVIEW_REQUIRED",
        "reason": "Publicación requiere revisión por potential IP/derechos de autor",
        "required_reviewers": ["abogado_ip", "abogado_admin"],
    },
    "accept_contract": {
        "default": "BLOCKED",
        "reason": "Aceptar contratos SIEMPRE requiere HITL del cliente + abogado",
        "required_reviewers": ["abogado", "cliente"],
    },
    "sign_document": {
        "default": "BLOCKED",
        "reason": "Firma requiere modo LIVE + autorización 2do factor + aprobación HITL",
        "required_reviewers": ["abogado", "cliente"],
    },
    "publish_legal_filing": {
        "default": "BLOCKED",
        "reason": "Presentación ante juzgado exige policy_mode=LIVE + aprobación HITL",
        "required_reviewers": ["abogado", "socio"],
    },
    "process_personal_data": {
        "default": "APPROVED_WITH_LIMITS",
        "reason": "Dato personal - Ley 1581 de 2012 - requiere consentimiento + finalidad",
        "limits": [
            "Consentimiento previo del titular",
            "Finalidad específica declarada",
            "Retención mínima necesaria",
        ],
    },
    "process_sensitive_data": {
        "default": "REVIEW_REQUIRED",
        "reason": "Dato sensible - requiere autorización expresa + revisión DPO",
        "required_reviewers": ["dpo", "abogado"],
        "limits": ["No almacenar en cloud", "Anonimizar si es posible"],
    },
    "send_external_communication": {
        "default": "REVIEW_REQUIRED",
        "reason": "Comunicación externa requiere HITL",
        "required_reviewers": ["abogado"],
    },
    "create_advertising": {
        "default": "REVIEW_REQUIRED",
        "reason": "Publicidad - Ley 1957 de 2019 (Colombia) - no garantías de resultados",
        "required_reviewers": ["abogado_etica"],
    },
    "use_third_party_content": {
        "default": "REVIEW_REQUIRED",
        "reason": "Contenido de terceros - verificar licencia y derechos",
        "required_reviewers": ["abogado_ip"],
    },
    "generate_legal_document": {
        "default": "APPROVED_WITH_LIMITS",
        "reason": "Generación de documentos requiere revisión por abogado",
        "limits": ["Plantilla revisada", "Citas verificadas", "Firma manual"],
    },
    "internal_research": {
        "default": "APPROVED",
        "reason": "Investigación interna sin acciones externas",
    },
    "tool_invocation": {
        "default": "APPROVED",
        "reason": "Invocación de tool interna - sujeta a RBAC + execution_guard",
    },
    "memory_storage": {
        "default": "APPROVED_WITH_LIMITS",
        "reason": "Almacenamiento en memoria - según clasificación",
        "limits": ["Sin credenciales", "Sin secretos técnicos"],
    },
    "export_evidence": {
        "default": "REVIEW_REQUIRED",
        "reason": "Exportar evidencia requiere HITL - puede contener secreto profesional",
        "required_reviewers": ["abogado"],
    },
}


class LegalGate:
    """Evaluates legal actions and returns one of 5 verdicts."""

    def __init__(self) -> None:
        self.log = get_logger("albra.legal_gate")

    def evaluate(
        self,
        action: str,
        *,
        text: str = "",
        actor_role: str = "anon",
        live_authorized: bool = False,
        approval_pending: bool = False,
        context: dict[str, Any] | None = None,
    ) -> LegalGateVerdict:
        ctx = context or {}
        rule = LEGAL_RULES.get(action)
        if not rule:
            return LegalGateVerdict(
                verdict="UNKNOWN",
                action=action,
                reason=f"No rule defined for action '{action}' - default UNKNOWN",
            )

        verdict = rule["default"]

        # Si action es LIVE y no autorizada → BLOCKED
        if action in ("publish_legal_filing", "sign_document", "accept_contract") and not live_authorized:
            verdict = "BLOCKED"
            return LegalGateVerdict(
                verdict=verdict,
                action=action,
                reason=f"{rule['reason']} - LIVE no autorizado",
                required_reviewers=rule.get("required_reviewers", []),
                evidence_required=True,
            )

        # Si hay approval HITL pendiente → REVIEW_REQUIRED
        if approval_pending:
            verdict = "REVIEW_REQUIRED"

        # Clasificación de datos
        classification_result = classify(text) if text else None
        classification = classification_result.classification.name if classification_result else ""

        # Datos sensibles/credenciales → BLOCKED si la action no es storage
        if classification_result and classification_result.classification in (
            DataClassification.CREDENCIAL,
            DataClassification.SECRETO_TECNICO,
        ) and action != "memory_storage":
            return LegalGateVerdict(
                verdict="BLOCKED",
                action=action,
                reason=f"Contiene {classification_result.label} - no puede usarse en {action}",
                classification=classification,
            )

        return LegalGateVerdict(
            verdict=verdict,
            action=action,
            reason=rule["reason"],
            limits=rule.get("limits", []),
            required_reviewers=rule.get("required_reviewers", []),
            evidence_required=verdict in ("REVIEW_REQUIRED", "BLOCKED"),
            classification=classification,
            metadata=ctx,
        )

    def list_rules(self) -> list[dict[str, Any]]:
        return [
            {
                "action": a,
                "default_verdict": r["default"],
                "reason": r["reason"],
                "limits": r.get("limits", []),
                "required_reviewers": r.get("required_reviewers", []),
            }
            for a, r in LEGAL_RULES.items()
        ]
