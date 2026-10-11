"""JWT-style token con HMAC-SHA256 (sin deps externas - stdlib only).

Tokens:
- signed with ALBRA_JWT_SECRET (config via env, NUNCA hardcodeado)
- payload: {sub, role, iat, exp}
- exp configurable (default 24h)
- verificar con hmac.compare_digest (constante-timing)

Formato: base64url(payload).base64url(signature)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

# Default expiry: 24h
DEFAULT_TOKEN_EXPIRY_SECONDS = 86400


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(s: str) -> bytes:
    padding = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + padding)


def _get_secret() -> bytes:
    """Lee ALBRA_JWT_SECRET del entorno. SIEMPRE debe configurarse en producción."""
    secret = os.environ.get("ALBRA_JWT_SECRET", "change-me-in-production")
    return secret.encode("utf-8")


def _sign(payload_b64: str, secret: bytes) -> str:
    return _b64encode(
        hmac.new(secret, payload_b64.encode("ascii"), hashlib.sha256).digest()
    )


def issue_token(
    *,
    subject: str,
    role: str,
    expires_in_seconds: int = DEFAULT_TOKEN_EXPIRY_SECONDS,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Emite un token firmado. El subject ya debe estar autenticado por otra vía."""
    now = time.time()
    payload = {
        "sub": subject,
        "role": role,
        "iat": int(now),
        "exp": int(now + expires_in_seconds),
    }
    if extra_claims:
        payload.update(extra_claims)
    payload_b64 = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = _sign(payload_b64, _get_secret())
    return f"{payload_b64}.{signature}"


def verify_token(token: str) -> dict[str, Any] | None:
    """Verifica firma + expiración. Devuelve payload o None si inválido/expirado."""
    if not token or "." not in token:
        return None
    parts = token.split(".", 1)
    if len(parts) != 2:
        return None
    payload_b64, signature = parts
    # Re-computar firma esperada (constante-timing)
    expected_signature = _sign(payload_b64, _get_secret())
    if not hmac.compare_digest(signature, expected_signature):
        return None
    try:
        payload = json.loads(_b64decode(payload_b64).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    # Check expiración
    if "exp" in payload and time.time() > payload["exp"]:
        return None
    if "sub" not in payload or "role" not in payload:
        return None
    return payload


def revoke_token(token: str) -> bool:
    """Tokens stateless no se pueden revocar sin blacklist.

    Para revocación real, integrar con redis blacklist o similar.
    Por ahora, rotar ALBRA_JWT_SECRET revoca todos los tokens.
    """
    return False  # not supported without external store
