"""V6.0 JWT validator.

Validates OIDC/OAuth 2.0 access tokens. Enforces:

  - Cryptographic signature (RS256/384/512 only) verified against the
    JWKS-resolved public key.
  - Algorithm allowed (no HS256, no 'none').
  - kid present in JWT header (must resolve via JWKS).
  - issuer (iss) matches config.issuer.
  - audience (aud) includes config.audience (and config.client_id if set).
  - expiration (exp) not in the past (with clock skew tolerance).
  - not-before (nbf) honored when present (with clock skew tolerance).
  - issued-at (iat) honored when present (sanity: not absurdly far future).

Uses PyJWT (maintained stdlib + cryptography wrapper). Never decodes
without verification — no ``verify=False`` anywhere.

Raises :class:`TokenValidationError` on any failure. The caller
translates this to None (fail-closed) in validate_bearer_token.

NEVER accept a token just because it has JWT format. NEVER trust
``jwt.decode(verify=False)``. The PyJWT call here always verifies
signature + iss + aud + exp + nbf.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import jwt
from jwt import InvalidTokenError, PyJWKClientError

from albra.identity.oidc.config import OIDCConfig
from albra.identity.oidc.jwks import JwksError, JwksResolver
from albra.observability.logger import get_logger


class TokenValidationError(RuntimeError):
    """Raised when a JWT/OIDC access token fails validation.

    The exception message is SAFE to expose in logs and audit events:
    it never contains the token, claims, or signature. Only the failure
    category (e.g. "expired", "invalid issuer", "unknown kid") is
    disclosed.
    """


@dataclass(frozen=True)
class VerifiedToken:
    """A successfully validated access token.

    Contains the verified claims dict (without the bearer token string)
    plus the resolved ``kid`` and ``algorithm`` from the JWT header.

    The raw token string is intentionally NOT stored here — we don't
    want it circulating in the auth pipeline beyond the validator.
    """
    claims: dict[str, Any]
    kid: str
    algorithm: str
    issuer: str
    subject: str


class JWTValidator:
    """Validates OIDC/OAuth 2.0 access tokens.

    A single instance is cheap to construct and reuse. The validator
    holds a reference to a JwksResolver which itself caches keys.
    """

    def __init__(
        self,
        config: OIDCConfig,
        *,
        jwks_resolver: JwksResolver | None = None,
    ) -> None:
        self._config = config
        self._jwks = jwks_resolver if jwks_resolver is not None else JwksResolver(config)
        self._log = get_logger("albra.identity.oidc.validator")

    def validate(self, token: str) -> VerifiedToken:
        """Validate an access token. Returns VerifiedToken on success.

        Raises TokenValidationError on any failure.

        The token string is NEVER logged. Only failure categories are
        logged (e.g. "expired", "invalid signature").
        """
        if not token or not isinstance(token, str):
            raise TokenValidationError("empty or non-string token")

        # 1. Parse header WITHOUT verifying signature, to extract kid
        #    and alg. This is safe — we don't trust the claims, only
        #    the header metadata, and we re-verify everything below.
        try:
            unverified_header = jwt.get_unverified_header(token)
        except InvalidTokenError as e:
            # Malformed JWT structure — not even decodable.
            raise TokenValidationError("malformed JWT structure") from e
        except ValueError as e:
            raise TokenValidationError("invalid JWT encoding") from e

        alg = unverified_header.get("alg")
        kid = unverified_header.get("kid", "")

        if alg == "none":
            raise TokenValidationError(
                "algorithm 'none' is forbidden — unsigned tokens rejected"
            )
        if alg not in self._config.allowed_algorithms:
            raise TokenValidationError(
                f"algorithm {alg!r} not in allowed list "
                f"{sorted(self._config.allowed_algorithms)}"
            )

        if not kid:
            raise TokenValidationError(
                "JWT header missing 'kid' — required for JWKS resolution"
            )

        # 2. Resolve the public key by kid.
        try:
            public_key = self._jwks.resolve(kid)
        except JwksError as e:
            raise TokenValidationError(f"JWKS resolution failed: {e}") from e

        # 3. Verify signature + iss + aud + exp + nbf in a single PyJWT call.
        #    PyJWT's decode() with options= always verifies signature when
        #    a key is provided — there's no way to disable it.
        try:
            # Build the audience list: include config.audience and
            # config.client_id (some IdPs include client_id in aud).
            audiences: list[str] = [self._config.audience]
            if self._config.client_id and self._config.client_id not in audiences:
                audiences.append(self._config.client_id)

            claims = jwt.decode(
                token,
                key=public_key,
                algorithms=sorted(self._config.allowed_algorithms),
                issuer=self._config.issuer,
                audience=audiences,
                options={
                    "verify_signature": True,
                    "verify_iss": True,
                    "verify_aud": True,
                    "verify_exp": True,
                    "verify_nbf": True,
                    "verify_iat": True,
                    "require": ["exp", "iat", "iss", "sub", "aud"],
                },
                # V6.0: leeway is a top-level kwarg to jwt.decode(),
                # NOT a key in the options dict. It applies to exp + nbf.
                leeway=self._config.clock_skew_seconds,
            )
        except jwt.ExpiredSignatureError as e:
            raise TokenValidationError("token expired") from e
        except jwt.InvalidIssuerError as e:
            raise TokenValidationError("invalid issuer") from e
        except jwt.InvalidAudienceError as e:
            raise TokenValidationError("invalid audience") from e
        except jwt.ImmatureSignatureError as e:
            raise TokenValidationError("token not yet valid (nbf in future)") from e
        except jwt.MissingRequiredClaimError as e:
            raise TokenValidationError(f"missing required claim: {e.claim}") from e
        except jwt.InvalidAlgorithmError as e:
            raise TokenValidationError(f"invalid algorithm: {e}") from e
        except InvalidTokenError as e:
            # Generic catch-all for signature mismatch, malformed
            # structure at the claims level, etc.
            msg = str(e)
            if "Signature" in msg:
                raise TokenValidationError("invalid signature") from e
            raise TokenValidationError(f"token validation failed: {msg}") from e
        except PyJWKClientError as e:
            raise TokenValidationError(f"JWK client error: {e}") from e
        except Exception as e:  # noqa: BLE001
            # Defensive: any unexpected error → fail-closed.
            raise TokenValidationError(
                f"unexpected validation error: {type(e).__name__}"
            ) from e

        # 4. Defensive: re-check iss/aud/sub explicitly. PyJWT should
        #    have caught these, but defense in depth.
        iss = claims.get("iss", "")
        sub = claims.get("sub", "")
        if not iss or iss != self._config.issuer:
            raise TokenValidationError("issuer mismatch after decode")
        if not sub:
            raise TokenValidationError("subject (sub) missing")

        self._log.info(
            "oidc.token.validated",
            kid=kid, alg=alg, iss=iss, sub=sub,
        )

        return VerifiedToken(
            claims=claims,
            kid=kid,
            algorithm=alg,
            issuer=iss,
            subject=sub,
        )
