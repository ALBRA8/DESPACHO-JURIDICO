"""V6.0 Identity abstraction.

Represents a stable logical identity derived from a verified OIDC token.

The stable identity is the tuple ``(issuer, subject)``. The subject (``sub``)
is provider-scoped and MUST NOT be treated as a global identifier — two
different issuers can assign the same ``sub`` to different users.

A SHA-256 of ``issuer||subject`` provides a stable opaque ``stable_id``
suitable for cross-referencing in logs and audit trails without leaking
the original issuer/sub values.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class Identity:
    """A stable logical identity derived from a verified OIDC token.

    Attributes:
        issuer: The verified ``iss`` claim (e.g. "https://albra.us.auth0.com/").
            Bound to a specific provider — see module docstring.
        subject: The verified ``sub`` claim, provider-scoped.
        stable_id: SHA-256 of ``issuer||subject``. Safe to log/audit.
        email: Optional email claim (metadata only — never used as
            security identity).
        name: Optional display name claim (metadata only).
        raw_claims: The full verified claims dict. Used downstream by
            RoleResolver/TenantResolver to look up trusted namespace
            claims. Never logged wholesale.
    """
    issuer: str
    subject: str
    stable_id: str = ""
    email: str = ""
    name: str = ""
    raw_claims: dict = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if not self.stable_id:
            object.__setattr__(
                self, "stable_id",
                _compute_stable_id(self.issuer, self.subject),
            )
        if self.raw_claims is None:
            object.__setattr__(self, "raw_claims", {})


def _compute_stable_id(issuer: str, subject: str) -> str:
    """SHA-256 of ``issuer||subject``. Returns hex digest."""
    h = hashlib.sha256()
    h.update(issuer.encode("utf-8"))
    h.update(b"\x00")  # separator to prevent concatenation ambiguity
    h.update(subject.encode("utf-8"))
    return h.hexdigest()


def build_identity_from_verified_token(verified) -> Identity:
    """Build an Identity from a VerifiedToken.

    Extracts email/name claims defensively. These are metadata only —
    they're never used for authorization decisions.
    """
    claims = verified.claims or {}
    email = str(claims.get("email") or "")
    name = str(claims.get("name") or "")
    return Identity(
        issuer=verified.issuer,
        subject=verified.subject,
        email=email,
        name=name,
        raw_claims=dict(claims),
    )
