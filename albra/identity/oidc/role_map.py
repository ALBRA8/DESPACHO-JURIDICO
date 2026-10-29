"""V6.0 Role resolution.

Maps a verified Identity to an ALBRA role (paralegal / abogado / socio
/ cliente / admin). Roles are ALBRA-internal — the OIDC provider
authenticates, ALBRA decides authorization.

Trusted claim sources (priority order):

1. ``OIDC_ROLE_NAMESPACE`` env var: the JWT claim namespace ALBRA trusts
   for role information. Default: ``"https://albra.dev"`` (Auth0-style
   namespaced claim). e.g. for Auth0 with namespace
   ``"https://albra.dev"``, the trusted claim is
   ``claims["https://albra.dev"]["role"]``.

2. The trusted claim name (default: ``"role"``).

3. The trusted role values (default: the 5 ALBRA roles).

CRITICAL: a bare ``claims["role"]`` claim (no namespace) is NEVER
trusted. An attacker who controls another IdP could mint a JWT with
``role: "admin"`` in the default namespace — ALBRA must not honor it.

Custom IdP integration: configure ``OIDC_ROLE_NAMESPACE`` to match
your IdP's namespace. If your IdP doesn't use namespaces, write a
custom RoleResolver subclass that maps your IdP's specific claim
format to ALBRA roles.

Production fail-closed:
    - If no role claim is found in the trusted namespace → DENY with
      RoleResolutionError("no trusted role claim").
    - If the role value is not in the allowed set → DENY with
      RoleResolutionError("role not allowed").
    - A bare unnamespaced role claim is NEVER used.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from albra.identity.oidc.identity import Identity
from albra.observability.logger import get_logger

# ALBRA roles — must match mcp/security.py ROLE_PERMISSIONS keys.
ALBRA_ROLES: frozenset[str] = frozenset({
    "paralegal", "abogado", "socio", "cliente", "admin",
})


class RoleResolutionError(RuntimeError):
    """Raised when a verified identity has no trusted ALBRA role.

    The error message is SAFE: it doesn't reveal which roles exist in
    the system.
    """


@dataclass
class RoleMapping:
    """Trusted role claim configuration.

    Attributes:
        namespace: The JWT claim namespace trusted for role info.
            Default: "https://albra.dev" (Auth0 convention).
            An EMPTY namespace means "trust bare unnamespaced claims"
            — this is INSECURE for production and only intended for
            tightly-controlled IdP integrations where you own the IdP
            and the claim.
        claim_name: The claim key inside the namespace (default "role").
        allowed_roles: Set of role values ALBRA accepts (default = the
            5 ALBRA roles).
    """
    namespace: str = "https://albra.dev"
    claim_name: str = "role"
    allowed_roles: frozenset[str] = ALBRA_ROLES

    @classmethod
    def from_env(cls) -> "RoleMapping":
        """Build RoleMapping from env vars."""
        return cls(
            namespace=os.environ.get("OIDC_ROLE_NAMESPACE", "https://albra.dev"),
            claim_name=os.environ.get("OIDC_ROLE_CLAIM", "role"),
            allowed_roles=ALBRA_ROLES,
        )


class RoleResolver:
    """Resolves an ALBRA role for a verified Identity.

    The resolver enforces the trusted-namespace policy: a bare
    unnamespaced ``role`` claim is NEVER used (unless the namespace
    is explicitly set to empty — production should never do this).
    """

    def __init__(self, mapping: RoleMapping | None = None) -> None:
        self._mapping = mapping or RoleMapping()
        self._log = get_logger("albra.identity.oidc.role_map")

    def resolve(self, identity: Identity) -> str:
        """Resolve the ALBRA role for an identity.

        Args:
            identity: Verified Identity.

        Returns:
            The ALBRA role (one of ALBRA_ROLES).

        Raises:
            RoleResolutionError: if no trusted role claim is found or
            the value is not allowed.
        """
        claims = identity.raw_claims or {}

        # 1. Look up the role claim in the trusted namespace.
        if self._mapping.namespace:
            ns_claim = claims.get(self._mapping.namespace)
            if not isinstance(ns_claim, dict):
                # No namespace claim at all → fail-closed.
                self._log.warning(
                    "oidc.role_resolution.denied_no_namespace",
                    namespace=self._mapping.namespace,
                    issuer=identity.issuer,
                )
                raise RoleResolutionError(
                    "no trusted role namespace claim found — identity "
                    "cannot be authorized"
                )
            role_value = ns_claim.get(self._mapping.claim_name)
        else:
            # Bare unnamespaced claim. INSECURE for production unless
            # you fully control the IdP. We still enforce the
            # allowed_roles whitelist.
            role_value = claims.get(self._mapping.claim_name)

        if not role_value or not isinstance(role_value, str):
            raise RoleResolutionError(
                "no trusted role claim value found"
            )

        if role_value not in self._mapping.allowed_roles:
            self._log.warning(
                "oidc.role_resolution.denied_role_not_allowed",
                issuer=identity.issuer,
                # DO NOT log the rejected role value — could be an
                # attacker-supplied string we don't want in logs.
            )
            raise RoleResolutionError(
                "role claim value is not in the allowed set"
            )

        self._log.info(
            "oidc.role_resolution.ok",
            issuer=identity.issuer, role=role_value,
        )
        return role_value
