"""
Políticas del Action Firewall.

Cada política define:
- action: nombre (ej. "send_external_message")
- risk: low | medium | high | critical
- requires_hitl: si requiere aprobación humana
- kill_switch: si se puede apagar en runtime
- audit_hash: si la traza debe ser hash-encadenada
- allowed_roles: roles que pueden ejecutar
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FirewallPolicy:
    action: str
    risk: str = "low"  # low | medium | high | critical
    requires_hitl: bool = False
    kill_switch: bool = True  # si se puede desactivar globalmente
    audit_hash: bool = True  # si la traza debe ser hash-encadenada
    allowed_roles: tuple[str, ...] = ("admin",)
    description: str = ""
    cooldown_seconds: int = 0  # 0 = sin cooldown
    metadata: dict[str, Any] = field(default_factory=dict)


# Políticas por defecto - pensadas para un despacho jurídico
FIREWALL_POLICIES: dict[str, FirewallPolicy] = {
    # --- Comunicaciones externas ---
    "send_external_message": FirewallPolicy(
        action="send_external_message",
        risk="high",
        requires_hitl=True,
        allowed_roles=("admin", "operator"),
        description="Enviar mensaje a canal externo (WhatsApp/Telegram/email)",
        cooldown_seconds=10,
    ),
    "publish_document": FirewallPolicy(
        action="publish_document",
        risk="critical",
        requires_hitl=True,
        kill_switch=False,  # nunca se apaga
        allowed_roles=("admin",),
        description="Publicar documento oficial",
    ),
    "send_legal_filing": FirewallPolicy(
        action="send_legal_filing",
        risk="critical",
        requires_hitl=True,
        kill_switch=False,
        allowed_roles=("admin",),
        description="Presentar escrito ante juzgado o autoridad",
    ),
    # --- Archivos ---
    "delete_evidence": FirewallPolicy(
        action="delete_evidence",
        risk="critical",
        requires_hitl=True,
        kill_switch=False,
        allowed_roles=("admin",),
        description="Eliminar evidencia - NUNCA permitido sin aprobación explícita",
    ),
    "modify_audit_log": FirewallPolicy(
        action="modify_audit_log",
        risk="critical",
        requires_hitl=False,  # NUNCA permitido
        kill_switch=False,
        allowed_roles=(),  # nadie
        description="Modificar log de auditoría - DENEGADO POR POLÍTICA",
    ),
    # --- Memoria ---
    "memory_write_knowledge": FirewallPolicy(
        action="memory_write_knowledge",
        risk="medium",
        requires_hitl=False,
        allowed_roles=("admin", "operator"),
        description="Escribir en la capa de conocimiento",
    ),
    "memory_purge": FirewallPolicy(
        action="memory_purge",
        risk="critical",
        requires_hitl=True,
        kill_switch=False,
        allowed_roles=("admin",),
        description="Purgar memoria - requiere aprobación explícita",
    ),
    # --- Configuración ---
    "modify_permissions": FirewallPolicy(
        action="modify_permissions",
        risk="high",
        requires_hitl=True,
        kill_switch=False,
        allowed_roles=("admin",),
        description="Modificar permisos de usuarios",
    ),
    "modify_config": FirewallPolicy(
        action="modify_config",
        risk="medium",
        requires_hitl=False,
        allowed_roles=("admin",),
        description="Modificar configuración operativa",
    ),
    # --- Herramientas ---
    "tool_invocation_low": FirewallPolicy(
        action="tool_invocation_low",
        risk="low",
        requires_hitl=False,
        allowed_roles=("anon", "user", "operator", "admin"),
        description="Invocar herramienta de riesgo bajo",
    ),
    "tool_invocation_medium": FirewallPolicy(
        action="tool_invocation_medium",
        risk="medium",
        requires_hitl=False,
        allowed_roles=("operator", "admin"),
        description="Invocar herramienta de riesgo medio",
    ),
    "tool_invocation_high": FirewallPolicy(
        action="tool_invocation_high",
        risk="high",
        requires_hitl=True,
        allowed_roles=("admin",),
        description="Invocar herramienta de riesgo alto",
    ),
    # --- Investigación ---
    "research_external": FirewallPolicy(
        action="research_external",
        risk="low",
        requires_hitl=False,
        allowed_roles=("user", "operator", "admin"),
        description="Investigación en fuentes externas",
    ),
    # --- Documentos ---
    "generate_legal_document": FirewallPolicy(
        action="generate_legal_document",
        risk="high",
        requires_hitl=True,
        allowed_roles=("admin", "operator"),
        description="Generar documento legal (demanda, contestación, etc.)",
    ),
}


def get_policy(action: str) -> FirewallPolicy | None:
    return FIREWALL_POLICIES.get(action)
