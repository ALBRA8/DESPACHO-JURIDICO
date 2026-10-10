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

P0 (password hashing): pbkdf2_hmac con salt aleatorio.
Nunca SHA-256 directo. Compatible con stdlib (sin deps externas).
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
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

# Parámetros pbkdf2 - 200k iteraciones (recomendado NIST 2023)
PBKDF2_ITERATIONS = 200_000
PBKDF2_ALGO = "sha256"
SALT_BYTES = 16


@dataclass
class AuthContext:
    user: str = "anon"
    role: str = "anon"
    authenticated: bool = False
    session: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


def hash_password(password: str) -> str:
    """Hash password con pbkdf2_hmac + salt aleatorio.

    Formato: pbkdf2$<iter>$<salt_hex>$<hash_hex>
    """
    salt = os.urandom(SALT_BYTES)
    derived = hashlib.pbkdf2_hmac(
        PBKDF2_ALGO, password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return f"pbkdf2${PBKDF2_ITERATIONS}${salt.hex()}${derived.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Verifica password contra stored hash (constante-timing)."""
    try:
        algo, iter_s, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2":
            return False
        iterations = int(iter_s)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
        derived = hashlib.pbkdf2_hmac(
            PBKDF2_ALGO, password.encode("utf-8"), salt, iterations
        )
        return hmac.compare_digest(derived, expected)
    except (ValueError, AttributeError):
        return False


class SecurityGate:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.log = get_logger("albra.security")
        self.hitl = HITLGate(settings)
        self._sessions: dict[str, AuthContext] = {}
        # Usuarios en memoria (producción: ir a DB/IDP)
        self._users: dict[str, dict[str, Any]] = {
            "admin": {
                "role": "admin",
                "password_hash": hash_password(self.settings.admin_password),
            },
        }

    async def login(self, user: str, password: str) -> AuthContext:
        record = self._users.get(user)
        if not record or not verify_password(password, record["password_hash"]):
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
        return secrets.token_hex(16)

    def register_user(self, user: str, password: str, role: str = "user") -> None:
        if role not in ROLE_LEVELS:
            raise ValueError(f"Rol inválido: {role}")
        self._users[user] = {"role": role, "password_hash": hash_password(password)}
        self.log.info("security.user.added", user=user, role=role)
