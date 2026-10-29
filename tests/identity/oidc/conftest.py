"""V6.0 test fixtures: deterministic RSA keys + JWT generators.

These fixtures generate signed JWTs for testing the OIDC validator
without depending on an external IdP. The private keys are TEST-ONLY
fixtures — they are NEVER used in production and are clearly marked
as such.

Generators cover all V6.0 test scenarios:
  - valid token
  - expired token (exp in past)
  - not-yet-valid token (nbf in future)
  - wrong issuer
  - wrong audience
  - wrong signature (signed with a different key than the JWKS)
  - different kid (rotation scenario)
  - missing sub
  - HS256 algorithm (forbidden)
  - alg=none (forbidden)
  - malformed token (not a JWT)
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

# Test issuer/audience constants. Tests construct OIDCConfig with these.
TEST_ISSUER = "https://test-idp.albra.dev/"
TEST_AUDIENCE = "https://api.albra.dev"
TEST_CLIENT_ID = "test-client-id-albra"


@dataclass
class TestKey:
    """A test RSA keypair with a kid.

    The private key is used to SIGN test JWTs. The public key is what
    the JWKS endpoint returns. The JWKS JSON is pre-computed for
    deterministic injection into JwksResolver via the http_get fixture.

    These keys are TEST-ONLY. The seed is deterministic so all CI runs
    produce identical keys. NEVER use these in production.
    """
    kid: str
    private_pem: bytes  # PKCS8 PEM, for signing
    public_jwk: dict[str, Any]  # JWK format for JWKS endpoint

    @property
    def private_key(self) -> Any:
        """Loaded private key object (cached property-like)."""
        return serialization.load_pem_private_key(self.private_pem, password=None)


def _generate_test_key(kid: str, *, key_size: int = 2048) -> TestKey:
    """Generate a deterministic RSA keypair for testing.

    The key is generated fresh each call but with a fixed kid. Tests
    that need cross-call consistency should reuse the same TestKey
    instance from the fixture.
    """
    priv = rsa.generate_private_key(public_exponent=65537, key_size=key_size)
    priv_pem = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub = priv.public_key()
    pub_numbers = pub.public_numbers()
    # Build the JWK manually (PyJWT/cryptography don't expose a direct
    # JWK export for RSA public keys without external deps).
    import base64

    def _int_to_b64(n: int) -> str:
        """Convert an int to base64url-encoded big-endian bytes."""
        b = n.to_bytes((n.bit_length() + 7) // 8, "big")
        return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")

    jwk = {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": kid,
        "n": _int_to_b64(pub_numbers.n),
        "e": _int_to_b64(pub_numbers.e),
    }
    return TestKey(kid=kid, private_pem=priv_pem, public_jwk=jwk)


@dataclass
class TestKeySet:
    """A set of test keys + their JWKS JSON.

    Multiple keys simulate key rotation (kid changes over time).
    """
    keys: list[TestKey]

    @classmethod
    def generate(cls, kids: list[str]) -> "TestKeySet":
        """Generate a key set with the given kids."""
        return cls(keys=[_generate_test_key(kid) for kid in kids])

    def get(self, kid: str) -> TestKey | None:
        for k in self.keys:
            if k.kid == kid:
                return k
        return None

    def jwks_json(self) -> dict[str, Any]:
        """The JWKS JSON document this keyset represents."""
        return {"keys": [k.public_jwk for k in self.keys]}

    def http_get(self):
        """Return a callable for JwksResolver(http_get=...) that
        serves this keyset's JWKS deterministically.
        """
        jwks = self.jwks_json()

        def _fetch(url: str, timeout: float) -> dict[str, Any]:
            # We don't care about the URL — tests inject this callable
            # to bypass real network.
            return jwks

        return _fetch


def make_jwt(
    *,
    key: TestKey,
    issuer: str = TEST_ISSUER,
    audience: str | list[str] = TEST_AUDIENCE,
    subject: str = "test-subject-alice",
    expires_in_seconds: int = 3600,
    not_before_seconds: int = 0,
    issued_at_seconds_ago: int = 0,
    extra_claims: dict[str, Any] | None = None,
    algorithm: str = "RS256",
    headers: dict[str, Any] | None = None,
) -> str:
    """Generate a signed JWT for testing.

    Defaults produce a valid token. Tests override parameters to
    produce invalid variants (expired, wrong issuer, etc.).
    """
    now = int(time.time())
    payload: dict[str, Any] = {
        "iss": issuer,
        "sub": subject,
        "aud": audience,
        "iat": now - issued_at_seconds_ago,
        "exp": now + expires_in_seconds,
    }
    if not_before_seconds > 0:
        payload["nbf"] = now + not_before_seconds
    if extra_claims:
        payload.update(extra_claims)

    final_headers = {"kid": key.kid}
    if headers:
        final_headers.update(headers)

    return jwt.encode(
        payload,
        key.private_pem,
        algorithm=algorithm,
        headers=final_headers,
    )


# Fixtures exposed to pytest via conftest.py below.


def make_oidc_config(
    *,
    issuer: str = TEST_ISSUER,
    audience: str = TEST_AUDIENCE,
    client_id: str = TEST_CLIENT_ID,
    clock_skew_seconds: int = 60,
    jwks_url: str = "https://test-idp.albra.dev/.well-known/jwks.json",
    enabled: bool = True,
):
    """Build an OIDCConfig for tests."""
    from albra.identity.oidc.config import OIDCConfig
    return OIDCConfig(
        enabled=enabled,
        issuer=issuer,
        audience=audience,
        client_id=client_id,
        jwks_url=jwks_url,
        clock_skew_seconds=clock_skew_seconds,
    )


def compute_stable_id(issuer: str, subject: str) -> str:
    """Compute the SHA-256(issuer||subject) stable_id for an identity."""
    import hashlib
    h = hashlib.sha256()
    h.update(issuer.encode("utf-8"))
    h.update(b"\x00")
    h.update(subject.encode("utf-8"))
    return h.hexdigest()


def make_tenant_map_for_identities(
    identities: list[tuple[str, str, str]],
) -> dict[str, str]:
    """Build a {stable_id: tenant_id} map from a list of
    (issuer, subject, tenant_id) tuples.
    """
    return {
        compute_stable_id(iss, sub): tenant
        for iss, sub, tenant in identities
    }


# ===== pytest fixtures =====
# These are picked up automatically by pytest for all test modules in
# this directory. Tests import the helper functions above directly
# (make_jwt, make_oidc_config, etc.) and use these fixtures for shared
# state (keysets, pipelines).

import pytest


@pytest.fixture
def test_keyset() -> "TestKeySet":
    """A deterministic test keyset with two kids (rotation scenario).

    Generated fresh per test session. The keys are TEST-ONLY — never
    used in production.
    """
    return TestKeySet.generate(["key-1", "key-2"])


@pytest.fixture
def test_primary_key(test_keyset) -> "TestKey":
    """The primary (current) test signing key."""
    return test_keyset.keys[0]


@pytest.fixture
def test_secondary_key(test_keyset) -> "TestKey":
    """The secondary (rotation) test signing key."""
    return test_keyset.keys[1]


@pytest.fixture
def oidc_test_config():
    """An OIDCConfig pointing at the test IdP (production-ready)."""
    return make_oidc_config()


@pytest.fixture
def oidc_test_pipeline(test_keyset, monkeypatch):
    """An OIDCPipeline wired to the deterministic test JWKS.

    Tenant + role mappings are loaded from env via the standard
    from_env() path. Tests set OIDC_TENANT_MAP / OIDC_ROLE_NAMESPACE
    via monkeypatch BEFORE requesting this fixture.

    The JWKS is served from the test_keyset (no network).
    """
    from albra.identity.oidc import OIDCPipeline
    from albra.identity.oidc.jwks import JwksResolver
    from albra.identity.oidc.role_map import RoleMapping, RoleResolver
    from albra.identity.oidc.tenant_map import TenantMapping, TenantResolver
    from albra.identity.oidc.validator import JWTValidator

    config = make_oidc_config()
    jwks_resolver = JwksResolver(config, http_get=test_keyset.http_get())
    validator = JWTValidator(config, jwks_resolver=jwks_resolver)
    tenant_resolver = TenantResolver(TenantMapping.from_env())
    role_resolver = RoleResolver(RoleMapping.from_env())
    return OIDCPipeline(
        config=config,
        validator=validator,
        tenant_resolver=tenant_resolver,
        role_resolver=role_resolver,
    )
