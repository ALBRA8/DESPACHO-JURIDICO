"""
Security Gate - autenticación y autorización.

Roles ALBRA:
- anon: solo chat básico
- user: puede usar tools low-risk
- operator: puede usar tools medium-risk, leer evidencia
- admin: todo lo anterior + alta de usuarios + cambios de config
- constructor: TODO (modificar código) - NO existe como rol runtime;
  el constructor vive fuera del agente, en GitHub.

Acciones sensibles SIEMPRE pasan por HITLGate.
"""
from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass, field
from typing import Any

from albra.config.settings import Settings
from albra.observability.logger import get_logger
from albra.security.hitl import HITLGate


ROLE_LEVELS = {
    "anon": 0,
    "user": 10,
    "operator": 50,
    "admin": 100,
}

TOOL_RISK_REQUIRED_ROLE = {
    "low": "anon",
    "medium": "operator",
    "high": "admin",
    "critical": "admin",  # + HITL obligatorio
}


@dataclass
class AuthContext:
    user: str = "anon"
    role: str = "anon"
    authenticated: bool = False
    session: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class SecurityGate:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.log = get_logger("albra.security")
        self.hitl = HITLGate(settings)
        self._sessions: dict[str, AuthContext] = {}
        # Usuarios en memoria (producción: ir a DB/IDP)
        self._users: dict[str, dict[str, Any]] = {
            "admin": {"role": "admin", "password_hash": self._hash(self.settings.admin_password)},
        }

    def _hash(self, password: str) -> str:
        return hashlib.sha256(password.encode("utf-8")).hexdigest()

    async def startup(self) -> None:
        self.log.info("security.startup", default_users=list(self._users.keys()))

    async def shutdown(self) -> None:
        self.log.info("security.shutdown")

    async def login(self, user: str, password: str) -> AuthContext:
        record = self._users.get(user)
        if not record or not hmac.compare_digest(self._hash(password), record["password_hash"]):
            self.log.warning("security.login.fail", user=user)
            return AuthContext(user=user, authenticated=False)
        ctx = AuthContext(
            user=user,
            role=record["role"],
            authenticated=True,
            session=self._new_session(),
            metadata={"login_at": time.time()},
        )
        self._sessions[ctx.session] = ctx
        self.log.info("security.login.ok", user=user, role=ctx.role)
        return ctx

    async def authorize(
        self,
        user: str,
        *,
        action: str,
        resource: str = "",
        risk: str = "low",
    ) -> AuthContext:
        """Verifica si un user puede ejecutar una acción."""
        ctx = self._find_ctx(user)
        required_role = TOOL_RISK_REQUIRED_ROLE.get(risk, "admin")
        if ROLE_LEVELS.get(ctx.role, 0) < ROLE_LEVELS.get(required_role, 100):
            ctx.metadata["allowed"] = False
            ctx.metadata["reason"] = f"role {ctx.role} < required {required_role}"
            return ctx
        # Acción sensible → HITL
        if action in self.settings.hitl_required_for:
            req = await self.hitl.request_approval(
                user=user, action=action, resource=resource, risk=risk
            )
            ctx.metadata["approval_request"] = req.as_dict()
            ctx.metadata["allowed"] = False
            ctx.metadata["reason"] = "pending_human_approval"
            return ctx

        ctx.metadata["allowed"] = True
        return ctx

    def _find_ctx(self, user: str) -> AuthContext:
        for s in self._sessions.values():
            if s.user == user:
                return s
        return AuthContext(user=user)

    def _new_session(self) -> str:
        import uuid
        return uuid.uuid4().hex

    def register_user(self, user: str, password: str, role: str = "user") -> None:
        if role not in ROLE_LEVELS:
            raise ValueError(f"Rol inválido: {role}")
        self._users[user] = {"role": role, "password_hash": self._hash(password)}
        self.log.info("security.user.added", user=user, role=role)
