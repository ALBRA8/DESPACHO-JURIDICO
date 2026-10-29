"""V6.0 Tenant resolution.

The tenant MUST be resolved from a server-side trusted mapping. A
client-supplied ``tenant_id`` (whether in args, headers, or JWT claims)
has NO authority — it is ignored.

Trusted mapping sources (in priority order):

1. ``OIDC_TENANT_MAP`` env var: JSON-encoded ``{stable_id: tenant_id}``
   map. Stable IDs are SHA-256(issuer||subject) hashes — opaque to
   attackers who don't have the issuer+sub combination.

2. ``OIDC_TENANT_MAP_PATH`` env var: path to a JSON file with the same
   structure. Loaded at construction; not re-read at runtime (a future
   feature could watch for changes).

3. Inline mapping passed at construction (for tests).

Production behavior:
    - If OIDC is enabled but no tenant map is configured → EVERY valid
      token is DENIED with TenantResolutionError("no tenant map").
    - If the stable_id is not in the map → DENIED with
      TenantResolutionError("identity not in tenant map").
    - If the stable_id maps to a tenant → that tenant is authoritative;
      client args cannot override it.

This closes the V5.2 contract: even a verified OIDC token cannot
escalate to another tenant by sending ``tenant_id`` in the request.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from albra.identity.oidc.identity import Identity
from albra.observability.logger import get_logger


class TenantResolutionError(RuntimeError):
    """Raised when a verified identity has no authorized tenant.

    The error message is SAFE to log: it does not reveal which other
    tenants exist or which identities are mapped.
    """


@dataclass
class TenantMapping:
    """Server-side trusted (stable_id → tenant_id) mapping.

    The mapping is immutable after construction. Mutations require a
    new TenantMapping instance (intentional: prevents accidental
    runtime drift).
    """
    mapping: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "TenantMapping":
        """Load the tenant map from env vars.

        Sources checked in order:
            1. OIDC_TENANT_MAP (JSON-encoded inline map)
            2. OIDC_TENANT_MAP_PATH (path to JSON file)

        Returns an empty mapping if neither is set. Empty mapping in
        production means every token is denied (fail-closed).
        """
        inline = os.environ.get("OIDC_TENANT_MAP")
        path = os.environ.get("OIDC_TENANT_MAP_PATH")
        data: dict[str, str] = {}

        if inline:
            try:
                parsed = json.loads(inline)
                if isinstance(parsed, dict):
                    data.update({str(k): str(v) for k, v in parsed.items()})
            except (json.JSONDecodeError, TypeError) as e:
                # Malformed map → treat as empty (production will deny).
                get_logger("albra.identity.oidc.tenant_map").warning(
                    "oidc.tenant_map.malformed_inline", error=str(e),
                )

        if path:
            try:
                with open(path, encoding="utf-8") as f:
                    parsed = json.load(f)
                if isinstance(parsed, dict):
                    data.update({str(k): str(v) for k, v in parsed.items()})
            except (OSError, json.JSONDecodeError, TypeError) as e:
                get_logger("albra.identity.oidc.tenant_map").warning(
                    "oidc.tenant_map.malformed_file", path=path, error=str(e),
                )

        return cls(mapping=data)

    def get_tenant(self, stable_id: str) -> str | None:
        """Return the tenant_id for a stable_id, or None if unmapped."""
        return self.mapping.get(stable_id)

    def is_empty(self) -> bool:
        return not self.mapping


class TenantResolver:
    """Resolves the authorized tenant for a verified Identity.

    The resolver is the ONLY authority for tenant in the auth pipeline.
    Client-supplied tenant_id is NEVER consulted here or downstream.
    """

    def __init__(self, mapping: TenantMapping | None = None) -> None:
        self._mapping = mapping or TenantMapping()
        self._log = get_logger("albra.identity.oidc.tenant_map")

    def resolve(self, identity: Identity) -> str:
        """Resolve the authorized tenant for an identity.

        Args:
            identity: Verified Identity from the JWT validator.

        Returns:
            The authorized tenant_id.

        Raises:
            TenantResolutionError: if the identity has no tenant
            mapping. The error message is SAFE — it does not reveal
            which tenants exist or who else is mapped.
        """
        if self._mapping.is_empty():
            # Production fail-closed: no tenant map configured → deny all.
            self._log.warning(
                "oidc.tenant_resolution.denied_no_map",
                stable_id_prefix=identity.stable_id[:8],
            )
            raise TenantResolutionError(
                "no tenant map configured — identity cannot be authorized "
                "to any tenant"
            )

        tenant = self._mapping.get_tenant(identity.stable_id)
        if not tenant:
            self._log.warning(
                "oidc.tenant_resolution.denied_unmapped",
                stable_id_prefix=identity.stable_id[:8],
                issuer=identity.issuer,
            )
            raise TenantResolutionError(
                "identity is not authorized for any tenant"
            )

        self._log.info(
            "oidc.tenant_resolution.ok",
            stable_id_prefix=identity.stable_id[:8],
            tenant_id=tenant,
        )
        return tenant
