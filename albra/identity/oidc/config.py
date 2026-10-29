"""V6.0 OIDC configuration.

Reads OIDC-related env vars at construction. In production, missing
required fields → fail-closed (raises ``OIDCConfigError``). Dev/test
modes can construct an empty config without raising.

Env vars (names chosen to be OIDC-standard + ALBRA prefix):

    OIDC_ENABLED        "true"/"false" — master switch for OIDC in prod.
                        Default: "false". When false in production,
                        validate_bearer_token(mode="production") still
                        returns None for every token (preserves V5.2
                        fail-closed behavior).
    OIDC_ISSUER         e.g. "https://albra.us.auth0.com/"
                        Required when OIDC_ENABLED=true.
    OIDC_AUDIENCE       e.g. "https://api.albra.dev"
                        Required when OIDC_ENABLED=true.
    OIDC_CLIENT_ID      Optional. Some IdPs require it as additional aud.
    OIDC_JWKS_URL       Optional override. If absent, discovered from
                        OIDC_ISSUER + "/.well-known/jwks.json".
                        Required for IdPs that don't follow standard
                        discovery.
    OIDC_CLOCK_SKEW_SECONDS  Default: 60. Tolerance for exp/nbf checks.

Production requirements (OIDC_ENABLED=true):
    OIDC_ISSUER + OIDC_AUDIENCE are mandatory. Missing → OIDCConfigError.

Production NEVER silently falls back to dev. If OIDC_ENABLED=false in
production mode, validate_bearer_token(mode="production") returns None
for every token (fail-closed correct, but no real auth).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


class OIDCConfigError(RuntimeError):
    """Raised when OIDC configuration is incomplete or invalid."""


def _env_str(key: str, default: str = "") -> str:
    val = os.environ.get(key)
    return val if val is not None else default


def _env_bool(key: str, default: bool = False) -> bool:
    val = os.environ.get(key)
    if val is None:
        return default
    return val.lower() in ("1", "true", "yes", "on")


def _env_int(key: str, default: int) -> int:
    val = os.environ.get(key)
    if val is None:
        return default
    try:
        return int(val)
    except ValueError:
        return default


# Algorithms accepted for production OIDC. RS256/384/512 only — symmetric
# algorithms (HS256) are explicitly forbidden because the JWKS flow is
# asymmetric-only by design. 'none' is NEVER accepted.
ALLOWED_ALGORITHMS: frozenset[str] = frozenset({"RS256", "RS384", "RS512"})


@dataclass
class OIDCConfig:
    """OIDC provider configuration.

    Construction is cheap and side-effect-free. The JwksResolver and
    JWTValidator are created lazily by the caller.
    """

    enabled: bool = False
    issuer: str = ""
    audience: str = ""
    client_id: str = ""
    jwks_url: str = ""
    clock_skew_seconds: int = 60
    allowed_algorithms: frozenset[str] = field(default_factory=lambda: ALLOWED_ALGORITHMS)
    # Network timeout for JWKS fetches (seconds).
    jwks_timeout_seconds: float = 5.0
    # TTL for the JWKS cache (seconds). Keys rotate; we re-fetch on
    # unknown kid AND on TTL expiry.
    jwks_cache_ttl_seconds: int = 600

    @classmethod
    def from_env(cls) -> "OIDCConfig":
        """Build an OIDCConfig from env vars.

        In production (ALBRA_ENVIRONMENT=production) with OIDC_ENABLED=true,
        missing OIDC_ISSUER or OIDC_AUDIENCE raises OIDCConfigError.
        """
        cfg = cls(
            enabled=_env_bool("OIDC_ENABLED", False),
            issuer=_env_str("OIDC_ISSUER"),
            audience=_env_str("OIDC_AUDIENCE"),
            client_id=_env_str("OIDC_CLIENT_ID"),
            jwks_url=_env_str("OIDC_JWKS_URL"),
            clock_skew_seconds=_env_int("OIDC_CLOCK_SKEW_SECONDS", 60),
            jwks_timeout_seconds=float(_env_int("OIDC_JWKS_TIMEOUT_SECONDS", 5)),
            jwks_cache_ttl_seconds=_env_int("OIDC_JWKS_CACHE_TTL_SECONDS", 600),
        )
        cfg._validate()
        return cfg

    def _validate(self) -> None:
        """Validate the config. Raises OIDCConfigError if invalid."""
        if not self.enabled:
            return
        errors: list[str] = []
        if not self.issuer:
            errors.append("OIDC_ISSUER is required when OIDC_ENABLED=true")
        if not self.audience:
            errors.append("OIDC_AUDIENCE is required when OIDC_ENABLED=true")
        if self.clock_skew_seconds < 0:
            errors.append("OIDC_CLOCK_SKEW_SECONDS must be >= 0")
        if self.jwks_timeout_seconds <= 0:
            errors.append("OIDC_JWKS_TIMEOUT_SECONDS must be > 0")
        if self.jwks_cache_ttl_seconds <= 0:
            errors.append("OIDC_JWKS_CACHE_TTL_SECONDS must be > 0")
        if errors:
            raise OIDCConfigError(
                "OIDC configuration is invalid: " + "; ".join(errors)
            )

    @property
    def resolved_jwks_url(self) -> str:
        """The JWKS URL to use. If jwks_url is set explicitly, use it.
        Otherwise derive from issuer + /.well-known/jwks.json (standard
        OIDC discovery).
        """
        if self.jwks_url:
            return self.jwks_url
        if not self.issuer:
            return ""
        # Strip trailing slash, then append standard OIDC discovery path.
        iss = self.issuer.rstrip("/")
        return f"{iss}/.well-known/jwks.json"

    def is_production_ready(self) -> bool:
        """True iff OIDC is enabled AND all required fields are present.
        When False, validate_bearer_token(mode="production") returns
        None for every token (fail-closed).
        """
        if not self.enabled:
            return False
        try:
            self._validate()
        except OIDCConfigError:
            return False
        return bool(self.issuer and self.audience and self.resolved_jwks_url)
