"""V6.0 OIDCPipeline: convenience bundler for the OIDC pipeline.

Bundles the four stateful components of the OIDC auth pipeline so
callers (McpHttpServer, tests, production deployments) can share a
single instance — critical for JWKS cache reuse across requests.

    OIDCPipeline(config)
        .config           — OIDCConfig
        .validator        — JWTValidator (holds JwksResolver with cache)
        .tenant_resolver  — TenantResolver
        .role_resolver     — RoleResolver

Usage in production (McpHttpServer):
    pipeline = OIDCPipeline.from_env()
    server = McpHttpServer(auth_mode="production", oidc_pipeline=pipeline)

Usage in tests:
    pipeline = OIDCPipeline(config, jwks_resolver=test_jwks,
                            tenant_resolver=test_tenant,
                            role_resolver=test_role)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from albra.identity.oidc.config import OIDCConfig
from albra.identity.oidc.jwks import JwksResolver
from albra.identity.oidc.role_map import RoleMapping, RoleResolver
from albra.identity.oidc.tenant_map import TenantMapping, TenantResolver
from albra.identity.oidc.validator import JWTValidator


@dataclass
class OIDCPipeline:
    """Bundle of OIDC pipeline components.

    A single instance is intended to be shared across requests in a
    production process. The JwksResolver caches JWKS keys; reusing
    the pipeline = reusing the cache.
    """
    config: OIDCConfig
    validator: JWTValidator
    tenant_resolver: TenantResolver
    role_resolver: RoleResolver

    @classmethod
    def from_env(
        cls,
        *,
        jwks_resolver: JwksResolver | None = None,
        tenant_mapping: TenantMapping | None = None,
        role_mapping: RoleMapping | None = None,
    ) -> "OIDCPipeline":
        """Build a pipeline from env vars.

        Each component can be overridden for tests. If not overridden,
        each loads its own config from env.
        """
        config = OIDCConfig.from_env()
        jwks = jwks_resolver if jwks_resolver is not None else JwksResolver(config)
        validator = JWTValidator(config, jwks_resolver=jwks)
        tenant = TenantResolver(tenant_mapping or TenantMapping.from_env())
        role = RoleResolver(role_mapping or RoleMapping.from_env())
        return cls(
            config=config,
            validator=validator,
            tenant_resolver=tenant,
            role_resolver=role,
        )

    @classmethod
    def for_testing(
        cls,
        config: OIDCConfig,
        *,
        jwks_http_get: Any = None,
        tenant_map: dict[str, str] | None = None,
        role_namespace: str = "https://albra.dev",
        role_claim: str = "role",
    ) -> "OIDCPipeline":
        """Build a pipeline for deterministic tests.

        Args:
            config: OIDCConfig (must be production-ready: enabled,
                issuer, audience set).
            jwks_http_get: Optional callable for JWKS fetch injection.
            tenant_map: Inline {stable_id: tenant_id} dict.
            role_namespace: Trusted namespace for role claims.
            role_claim: Claim name inside the namespace.
        """
        jwks = JwksResolver(config, http_get=jwks_http_get) if jwks_http_get else JwksResolver(config)
        validator = JWTValidator(config, jwks_resolver=jwks)
        tenant = TenantResolver(TenantMapping(mapping=tenant_map or {}))
        role = RoleResolver(RoleMapping(
            namespace=role_namespace, claim_name=role_claim,
        ))
        return cls(
            config=config,
            validator=validator,
            tenant_resolver=tenant,
            role_resolver=role,
        )
