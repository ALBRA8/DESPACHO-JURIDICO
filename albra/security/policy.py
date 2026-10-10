"""
Policy-as-Code - reglas declarativas que el agente cumple.

Las políticas son versionadas, auditables, y se cargan como conocimiento
(NO como código). El PolicyEngine las evalúa contra un contexto.

Ejemplos de políticas:
- "Si expediente involucra menor de edad → requiere abogado especialista en infancia"
- "Si monto > 1000 SMMLV → requiere aprobación del socio"
- "Si jurisdicción=CO y materia=laboral → aplicar Ley 721 de 2001"
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from albra.observability.logger import get_logger


@dataclass
class Policy:
    id: str
    name: str
    description: str
    rule: str  # expresión simple: "field op value"
    action: str = "deny"  # deny | warn | require_hitl | require_role
    required_role: str | None = None
    jurisdiction: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PolicyEvalResult:
    policy_id: str
    triggered: bool
    action: str
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "triggered": self.triggered,
            "action": self.action,
            "reason": self.reason,
        }


# Operadores soportados
OPS = {
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    ">": lambda a, b: float(a) > float(b),
    "<": lambda a, b: float(a) < float(b),
    ">=": lambda a, b: float(a) >= float(b),
    "<=": lambda a, b: float(a) <= float(b),
    "in": lambda a, b: a in b,
    "not_in": lambda a, b: a not in b,
    "contains": lambda a, b: str(b) in str(a),
}


class PolicyEngine:
    """Motor de evaluación de políticas."""

    def __init__(self) -> None:
        self.log = get_logger("albra.policy")
        self._policies: dict[str, Policy] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        defaults = [
            Policy(
                id="CO-001",
                name="menor_edad_abogado_especialista",
                description="Expedientes con menores requieren especialista en infancia",
                rule="subject_contains:menor",
                action="require_role",
                required_role="specialist_family",
                jurisdiction="CO",
            ),
            Policy(
                id="CO-002",
                name="monto_alto_aprobacion_socio",
                description="Montos superiores a 1000 SMMLV requieren HITL",
                rule="amount:>:1000",
                action="require_hitl",
                jurisdiction="CO",
            ),
            Policy(
                id="GLOBAL-001",
                name="no_modificar_audit",
                description="NUNCA modificar el log de auditoría",
                rule="action==:modify_audit_log",
                action="deny",
            ),
            Policy(
                id="GLOBAL-002",
                name="no_envio_externo_sin_aprobacion",
                description="Envío a canal externo requiere HITL",
                rule="action==:send_external_message",
                action="require_hitl",
            ),
            Policy(
                id="GLOBAL-003",
                name="datos_sensibles_modelo_local",
                description="Datos sensibles van a modelo local",
                rule="subject_contains:cliente OR subject_contains:dni",
                action="warn",
            ),
        ]
        for p in defaults:
            self._policies[p.id] = p
        self.log.info("policies.registered", count=len(self._policies))

    def register(self, policy: Policy) -> None:
        if policy.id in self._policies:
            raise ValueError(f"Policy '{policy.id}' ya existe")
        self._policies[policy.id] = policy
        self.log.info("policy.added", id=policy.id, name=policy.name)

    def evaluate(self, context: dict[str, Any]) -> list[PolicyEvalResult]:
        """Evalúa todas las políticas aplicables a un contexto."""
        results: list[PolicyEvalResult] = []
        jurisdiction = context.get("jurisdiction")
        for p in self._policies.values():
            if p.jurisdiction and p.jurisdiction != jurisdiction:
                continue
            triggered = self._eval_rule(p.rule, context)
            if triggered:
                results.append(PolicyEvalResult(
                    policy_id=p.id,
                    triggered=True,
                    action=p.action,
                    reason=p.description,
                ))
        return results

    def _eval_rule(self, rule: str, context: dict[str, Any]) -> bool:
        """Evalúa una regla simple contra el contexto.

        Formatos soportados:
        - "field op value"  (ej: "amount > 1000")
        - "field_contains:value" (substring)
        - "field==:value"
        - "expr1 OR expr2"
        """
        # Soporte OR simple
        if " OR " in rule:
            return any(self._eval_rule(p, context) for p in rule.split(" OR "))
        if " AND " in rule:
            return all(self._eval_rule(p, context) for p in rule.split(" AND "))

        # Pattern field_op:value o field op value
        for op_str in OPS:
            if f" {op_str} " in rule:
                parts = rule.split(f" {op_str} ", 1)
                field = parts[0].strip()
                value = parts[1].strip()
                field_val = context.get(field)
                if field_val is None:
                    return False
                try:
                    return OPS[op_str](field_val, value)
                except Exception:  # noqa: BLE001
                    return False

        # Pattern field_contains:value
        if "_contains:" in rule:
            field, val = rule.split("_contains:", 1)
            field_val = context.get(field.strip())
            if field_val is None:
                return False
            return val.strip().lower() in str(field_val).lower()

        # Pattern field==:value (más simple)
        if "==:" in rule:
            field, val = rule.split("==:", 1)
            return str(context.get(field.strip())) == val.strip()

        return False

    def list(self) -> list[dict[str, Any]]:
        return [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "rule": p.rule,
                "action": p.action,
                "jurisdiction": p.jurisdiction,
                "required_role": p.required_role,
            }
            for p in self._policies.values()
        ]
