"""
APPROVAL CHAIN — workflow Suggest → Prepare → Approve → Execute → Record
con `minimum_human_signoff` obligatorio.

Inspirado en Claude-Code-Law-Firm (`minimum_human_signoff`), GLAW (Chief/Council
approval), Lavern (human gates), Prism (review-and-approvals), LawPortal
(Suggest→Prepare→Approve→Execute→Record).

Cada acción que toca al cliente declara `minimum_human_signoff`:
- `publish_legal_filing`    → 1 firma (abogado o superior)
- `sign_document`            → 1 firma (abogado o superior)
- `accept_contract`          → 2 firmas (abogado + cliente)
- `send_external_message`    → 1 firma (abogado o superior)

REGLA CRÍTICA: el agente NUNCA puede saltarse la cadena sin importar su confianza.
Esto es `abdicación explícita de autonomía` (Ley 1123/2007 — ética abogadil).

Flujo:
1. Suggest  — el agente propone la acción con descripción + payload
2. Prepare  — el agente prepara el payload final (p. ej. genera el documento a firmar)
3. Approve  — el abogado calificado firma. Se necesitan `minimum_human_signoff` firmas.
4. Execute  — tras la última firma, la acción se ejecuta.
5. Record   — el resultado se persiste en audit log (Etapa 5).

Materialización en state machine del matter:
- Cuando el matter llega a `EN-ESPERA-DE-APROBACIÓN`, las pending_actions
  se materializan como `AWAITING-PARTNER` gate.
- Sin aprobación → el state machine no puede avanzar a `LISTO-PARA-CLIENTE`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from albra.observability.logger import get_logger

# Default minimum_human_signoff por tipo de acción
# (puede sobreescribirse al crear la acción pendiente)
DEFAULT_SIGNOFF_BY_ACTION: dict[str, int] = {
    "publish_legal_filing": 1,    # radicación ante juez → abogado
    "sign_document":         1,    # firma de documentos → abogado
    "send_external_message": 1,    # comunicación externa → abogado
    "accept_contract":      2,    # aceptar contrato → abogado + cliente
    "modify_permissions":   2,    # cambios de permisos → socio + abogado
    "financial_action":     2,    # transacciones financieras → socio + abogado
    "publish_document":     1,    # publicación de documentos → abogado
    "legal_filing":         1,    # radicación legal → abogado
}

# Roles válidos para firmar (en orden jerárquico)
SIGNOFF_ROLE_HIERARCHY: dict[str, int] = {
    "paralegal": 1,
    "abogado": 2,
    "socio": 3,
    "cliente": 4,  # cliente puede firmar contratos pero NO decisiones técnicas
}

# Roles válidos para firmar acciones técnicas
TECHNICAL_ROLES: frozenset[str] = frozenset({"abogado", "socio"})


class ApprovalChainError(RuntimeError):
    """Cualquier error en la cadena de aprobación."""


class InsufficientSignoffsError(ApprovalChainError):
    """Cuando se intenta ejecutar sin todas las firmas requeridas."""


class UnauthorizedRoleError(ApprovalChainError):
    """Cuando un rol no autorizado intenta firmar."""


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class ApprovalChainEntry:
    """Snapshot inmutable de la cadena en un momento dado."""
    action_id: str
    matter_id: str
    action_type: str
    description: str
    minimum_human_signoff: int
    approvals: list[dict[str, str]] = field(default_factory=list)
    status: str = "PENDING"  # PENDING | APPROVED | REJECTED | EXECUTED | RECORDED


class ApprovalChain:
    """Orquestador de la cadena Suggest → Prepare → Approve → Execute → Record.

    Depende de MatterStore (que persiste pending_actions) y expone métodos
    de alto nivel que validan roles, jerarquía y `minimum_human_signoff`.
    """

    def __init__(self, matter_store: Any) -> None:
        """
        Args:
            matter_store: instancia de albra.matters.store.MatterStore
        """
        self.store = matter_store
        self.log = get_logger("albra.security.approval_chain")

    # ===== Paso 1: Suggest =====

    def suggest(
        self,
        *,
        matter_id: str,
        action_type: str,
        description: str,
        payload: dict[str, Any] | None = None,
        tenant_id: str | None = None,
    ) -> str:
        """El agente propone una acción. Crea pending_action con
        `minimum_human_signoff` default para el action_type.

        NO puede ejecutarse todavía. Solo queda PENDING.

        V5.2: ``tenant_id`` is threaded to ``MatterStore.create_pending_action``.
        Under ``enforce_tenant=True`` (production), this raises
        ``TenantAuthorizationError`` if tenant_id is missing/placeholder,
        and ``KeyError`` if the matter_id does not belong to the
        authorized tenant. No partial pending action is ever persisted
        on a cross-tenant matter.
        """
        signoffs = DEFAULT_SIGNOFF_BY_ACTION.get(action_type, 1)
        if signoffs < 1:
            signoffs = 1
        action_id = self.store.create_pending_action(
            matter_id=matter_id,
            action_type=action_type,
            description=description,
            minimum_human_signoff=signoffs,
            tenant_id=tenant_id,
        )
        self.log.info(
            "approval.suggest",
            action_id=action_id, matter_id=matter_id,
            action_type=action_type, minimum_signoff=signoffs,
            tenant_id=tenant_id,
        )
        return action_id

    # ===== Paso 2: Prepare =====
    # (En V2.0 el payload se pasa en suggest. Prepare es una anotación
    # de que el payload está listo. Para V2.1 podría ser un método async
    # que invoca DRAFTING-AGENT.)
    # Omitido como método separado; se asume que el payload va en suggest.

    # ===== Paso 3: Approve =====

    def approve(
        self,
        action_id: str,
        *,
        by: str,
        role: str,
        comment: str = "",
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        """El abogado firma. Si es la última firma requerida, el status pasa a APPROVED.

        Reglas:
        - Solo roles TÉCNICOS (abogado, socio) pueden firmar acciones técnicas.
        - El rol cliente puede firmar contratos (accept_contract).
        - No se puede firmar una acción ya decidida (APPROVED/REJECTED/EXECUTED).

        V5.1: ``tenant_id`` is threaded through to ``MatterStore`` so that
        cross-tenant approve is blocked at the storage layer. The CLI's
        production guard prevents unauthorized callers from reaching this
        path in production; the tenant_id parameter is defense-in-depth.
        """
        action = self.store.get_pending_action(action_id, tenant_id=tenant_id)
        if not action:
            raise ApprovalChainError(f"Pending action not found: {action_id}")
        if action["status"] != "PENDING":
            raise ApprovalChainError(
                f"Action {action_id} status={action['status']} (must be PENDING)"
            )

        # Validar role
        if role not in SIGNOFF_ROLE_HIERARCHY:
            raise UnauthorizedRoleError(
                f"Unknown role: {role!r}. Valid: {list(SIGNOFF_ROLE_HIERARCHY)}"
            )

        # Validar que el rol puede firmar esta acción
        action_type = action["action_type"]
        if action_type in {"publish_legal_filing", "sign_document",
                           "send_external_message", "publish_document",
                           "legal_filing"}:
            # Solo roles técnicos
            if role not in TECHNICAL_ROLES:
                raise UnauthorizedRoleError(
                    f"Action {action_type} requires technical role "
                    f"({sorted(TECHNICAL_ROLES)}). Got: {role}"
                )
        elif action_type == "accept_contract":
            # Requiere abogado + cliente (mínimo 2 firmas)
            # Verificamos que la firma actual sea válida
            existing_roles = {a["role"] for a in action["approvals"]}
            # Si ya hay una firma de abogado, esta debe ser cliente y viceversa
            # (regla simplificada: ambas firmas deben ser de roles distintos)
            if role in existing_roles and len(action["approvals"]) < 2:
                raise UnauthorizedRoleError(
                    f"accept_contract requires 2 DIFFERENT roles. "
                    f"Role {role!r} already signed. Need a different role."
                )
            if role not in {"abogado", "socio", "cliente"}:
                raise UnauthorizedRoleError(
                    f"accept_contract requires abogado/socio or cliente role. Got: {role}"
                )
        elif action_type in {"modify_permissions", "financial_action"}:
            # Requiere socio + abogado
            if role not in {"abogado", "socio"}:
                raise UnauthorizedRoleError(
                    f"Action {action_type} requires socio or abogado. Got: {role}"
                )

        # Delegar al store para añadir la firma
        updated = self.store.add_approval(
            action_id, by=by, role=role, comment=comment, tenant_id=tenant_id,
        )
        self.log.info(
            "approval.approve",
            action_id=action_id, by=by, role=role,
            status=updated["status"],
            approvals_count=len(updated["approvals"]),
            minimum=updated["minimum_human_signoff"],
        )
        return updated

    # ===== Paso 3': Reject =====

    def reject(
        self,
        action_id: str,
        *,
        by: str,
        role: str,
        comment: str = "",
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        """El abogado rechaza la acción propuesta. Status pasa a REJECTED.

        Cualquier rol técnico puede rechazar (paralegal no).

        V5.1: ``tenant_id`` is threaded to the store to block cross-tenant
        rejects. The store raises KeyError on cross-tenant access (so we
        don't leak whether the action exists); we wrap it as
        ApprovalChainError for API consistency with approve().
        """
        if role not in TECHNICAL_ROLES:
            raise UnauthorizedRoleError(
                f"Reject requires technical role. Got: {role!r}"
            )
        try:
            return self.store.reject_action(
                action_id, by=by, role=role, comment=comment, tenant_id=tenant_id,
            )
        except KeyError as e:
            # V5.1: wrap as ApprovalChainError for API consistency with approve().
            # The store's KeyError is implementation detail; the public API
            # surface of ApprovalChain must be uniform.
            raise ApprovalChainError(str(e)) from e

    # ===== Paso 4: Execute =====

    def can_execute(self, action_id: str, *, tenant_id: str | None = None) -> tuple[bool, str]:
        """Verifica si la acción puede ejecutarse.

        Returns:
            (can_execute, reason) — reason explica por qué no si can_execute=False.

        V5.1: ``tenant_id`` is threaded to ``get_pending_action`` so that
        cross-tenant ``can_execute`` checks return False (action not found
        from the perspective of the requesting tenant).
        """
        action = self.store.get_pending_action(action_id, tenant_id=tenant_id)
        if not action:
            return False, f"Action {action_id} not found"
        if action["status"] == "REJECTED":
            return False, f"Action was rejected by {action['decided_by']}"
        if action["status"] == "PENDING":
            return False, (
                f"Action pending: {len(action['approvals'])}/"
                f"{action['minimum_human_signoff']} approvals"
            )
        if action["status"] == "EXECUTED":
            return False, "Action already executed"
        if action["status"] == "RECORDED":
            return False, "Action already recorded"
        if action["status"] == "APPROVED":
            return True, "All approvals received"
        return False, f"Unknown status: {action['status']}"

    # ===== Paso 5: Record =====
    # (La persistencia en audit log la hace MatterAudit en Etapa 5.
    # Aquí solo marcamos el status EXECUTED.)

    def mark_executed(self, action_id: str, *, by: str, tenant_id: str | None = None) -> dict[str, Any]:
        """Marca la acción como EXECUTED. Llamar después de ejecutar el efecto real.

        V5.2 audit: this method has a direct SQL ``UPDATE pending_actions``
        write (lines below). The independent V5.2 audit required verifying
        that no ApprovalChain method bypasses the store's tenant checks.

        The direct SQL write is safe because it is preceded by two tenant
        verifications:

          1. ``self.store.get_pending_action(action_id, tenant_id=...)``
             returns ``None`` if the action's matter does not belong to
             the authorized tenant. We raise ``ApprovalChainError`` in
             that case BEFORE the SQL write.
          2. ``self.can_execute(action_id, tenant_id=...)`` re-verifies
             the tenant via ``get_pending_action`` and returns ``False``
             if the action is not found from the tenant's perspective.

        By the time the direct SQL ``UPDATE pending_actions SET
        status='EXECUTED' WHERE id=?`` runs, the ``action_id`` has been
        verified to belong to the authorized tenant AND its status is
        ``APPROVED``. The UPDATE is therefore scoped to a verified row.

        No bypass exists. The direct SQL is left in place because
        refactoring it into a new ``MatterStore.mark_action_executed``
        method is out of scope for V5.2 (would be a feature, not a
        security fix). A future refactor should consolidate the write
        into the store layer for consistency with ``add_approval`` and
        ``reject_action``.
        """
        action = self.store.get_pending_action(action_id, tenant_id=tenant_id)
        if not action:
            raise ApprovalChainError(f"Pending action not found: {action_id}")
        can_exec, reason = self.can_execute(action_id, tenant_id=tenant_id)
        if not can_exec:
            raise InsufficientSignoffsError(
                f"Cannot execute action {action_id}: {reason}"
            )
        # V5.2 audit: action_id has been verified to belong to the
        # authorized tenant (via get_pending_action + can_execute above).
        # The direct SQL UPDATE below is therefore scoped to a verified
        # row. See the method docstring for the full audit trail.
        self.store._conn.execute(
            "UPDATE pending_actions SET status = 'EXECUTED', decided_at = ?, decided_by = ? "
            "WHERE id = ?",
            (_utcnow_iso(), by, action_id),
        )
        self.store._conn.commit()
        self.log.info("approval.executed", action_id=action_id, by=by)
        return self.store.get_pending_action(action_id, tenant_id=tenant_id) or action

    # ===== Inspección =====

    def list_pending_for_matter(self, matter_id: str, *, tenant_id: str | None = None) -> list[dict[str, Any]]:
        return self.store.list_pending(matter_id=matter_id, tenant_id=tenant_id)

    def list_all_pending(self, *, tenant_id: str | None = None) -> list[dict[str, Any]]:
        return self.store.list_pending(tenant_id=tenant_id)

    def get_status(self, action_id: str, *, tenant_id: str | None = None) -> dict[str, Any] | None:
        return self.store.get_pending_action(action_id, tenant_id=tenant_id)
