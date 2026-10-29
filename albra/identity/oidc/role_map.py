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
your IdP's namespace. The namespace MUST be a non-empty string (any
explicit namespace is allowed — e.g. ``https://albra8.com/claims``,
``https://albra.dev``, ``https://keycloak.albra.dev/realms/albra``).
An empty namespace is FORBIDDEN — see V6.0.1 below.

V6.0.1 HARDENING — fail-closed on empty namespace:
    The V6.0 RoleResolver had a code path where
    ``OIDC_ROLE_NAMESPACE=""`` fell through to
    ``claims.get(self._mapping.claim_name)`` — accepting the bare
    ``role`` claim. This contradicted the V6.0 contract
    "bare role NEVER trusted".

    V6.0.1 closes this with TWO independent layers of defense:

      1. ``RoleMapping.from_env()`` validates the namespace at
         construction time. An empty namespace raises
         ``RoleResolutionError("OIDC_ROLE_NAMESPACE is empty — bare
         role claims are never trusted")``.

      2. ``RoleResolver.resolve()`` independently refuses to look
         up a role claim when ``self._mapping.namespace`` is empty,
         even if a misconfigured RoleMapping somehow reaches the
         resolver. This is defense-in-depth: a future code path
         that constructs RoleMapping without going through
         ``from_env()`` cannot accidentally enable bare role trust.

    Behavior matrix:
      - namespace explicit (e.g. ``https://albra.dev``) → look up
        ``claims[namespace][claim_name]``. Missing namespace claim →
        DENY. Bare ``role`` claim → DENY (always).
      - namespace empty → DENY (fail-closed at config + resolver).
      - namespace unset → defaults to ``https://albra.dev``.

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
            V6.0.1: an EMPTY namespace is FORBIDDEN. The RoleResolver
            will refuse to look up a role claim when namespace is empty,
            even if a misconfigured RoleMapping reaches the resolver
            without going through ``from_env()`` (defense in depth).
        claim_name: The claim key inside the namespace (default "role").
        allowed_roles: Set of role values ALBRA accepts (default = the
            5 ALBRA roles).
    """
    namespace: str = "https://albra.dev"
    claim_name: str = "role"
    allowed_roles: frozenset[str] = ALBRA_ROLES

    @classmethod
    def from_env(cls) -> "RoleMapping":
        """Build RoleMapping from env vars.

        V6.0.1: if OIDC_ROLE_NAMESPACE is explicitly set to an empty
        string, raises RoleResolutionError. An empty namespace would
        enable bare ``role`` claim trust, which contradicts the V6.0
        contract.
        """
        namespace = os.environ.get("OIDC_ROLE_NAMESPACE", "https://albra.dev")
        # V6.0.1: empty namespace is forbidden. Fail-closed at config.
        if not namespace or not namespace.strip():
            raise RoleResolutionError(
                "OIDC_ROLE_NAMESPACE is empty — bare role claims are "
                "never trusted. Set an explicit namespace (e.g. "
                "https://albra.dev or https://albra8.com/claims) or "
                "unset the variable to use the default."
            )
        return cls(
            namespace=namespace,
            claim_name=os.environ.get("OIDC_ROLE_CLAIM", "role"),
            allowed_roles=ALBRA_ROLES,
        )


class RoleResolver:
    """Resolves an ALBRA role for a verified Identity.

    The resolver enforces the trusted-namespace policy: a bare
    unnamespaced ``role`` claim is NEVER used.

    V6.0.1: even if a misconfigured RoleMapping with an empty namespace
    reaches this resolver, it refuses to look up the role claim and
    raises RoleResolutionError. This is defense-in-depth: the
    ``RoleMapping.from_env()`` factory already rejects empty namespaces,
    but the resolver independently re-validates to catch any future code
    path that bypasses the factory.
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

        # V6.0.1: defense in depth — refuse empty namespace at the
        # resolver boundary, even if a misconfigured RoleMapping reached
        # us. This catches any future code path that bypasses
        # RoleMapping.from_env(). The previous V6.0 code fell through
        # to claims.get(claim_name) here, enabling bare role trust.
        if not self._mapping.namespace or not self._mapping.namespace.strip():
            self._log.warning(
                "oidc.role_resolution.denied_empty_namespace",
                issuer=identity.issuer,
            )
            raise RoleResolutionError(
                "OIDC_ROLE_NAMESPACE is empty — bare role claims are "
                "never trusted"
            )

        # Look up the role claim in the trusted namespace.
        # namespace is guaranteed non-empty here.
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
