"""V6.0 JWKS resolver.

Resolves RSA public keys by ``kid`` from a JWKS endpoint. Implements:

  - In-memory cache keyed by ``kid``.
  - TTL-based cache expiry (default 600s). On TTL expiry, the next
    request re-fetches the entire JWKS.
  - On unknown ``kid`` (key rotation event), re-fetches the JWKS once.
    If the new JWKS still lacks the kid → raises ``JwksError``.
  - Network timeout (default 5s). Never blocks indefinitely.
  - Thread-safe (single lock around cache mutation).
  - No private keys are ever stored. The JWKS endpoint only returns
    public keys (JWK with ``kty=RSA``, ``use=sig``, ``n``, ``e``).
"""
from __future__ import annotations

import threading
import time
from typing import Any

from jwt import PyJWKClientError
from jwt.algorithms import RSAAlgorithm

from albra.identity.oidc.config import OIDCConfig
from albra.observability.logger import get_logger


class JwksError(RuntimeError):
    """Raised when a JWKS lookup fails or the kid is unknown."""


class JwksResolver:
    """Resolves RSA public keys by ``kid`` from a JWKS endpoint.

    The resolver is stateful (caches keys) but thread-safe. Multiple
    McpHttpServer instances can share a single resolver; in practice
    each McpHttpServer constructs its own.
    """

    def __init__(
        self,
        config: OIDCConfig,
        *,
        http_get: Any = None,
    ) -> None:
        """Args:
            config: OIDCConfig with jwks_url resolved.
            http_get: Optional callable ``(url, timeout) -> dict`` for
                fetching the JWKS. Defaults to a stdlib-only urllib
                implementation. Tests inject a deterministic callable.
        """
        self._config = config
        self._log = get_logger("albra.identity.oidc.jwks")
        self._lock = threading.Lock()
        self._cache: dict[str, Any] = {}  # kid → public key object
        self._cache_fetched_at: float = 0.0
        self._http_get = http_get or self._default_http_get

    def _default_http_get(self, url: str, timeout: float) -> dict[str, Any]:
        """Stdlib JWKS fetcher. Returns the parsed JWKS dict.

        V6.0 design note: we use urllib (stdlib) instead of httpx here
        because the JWKS path is rare (cold start + key rotation) and
        keeping stdlib-only avoids coupling the OIDC layer to httpx.
        Tests inject their own ``http_get`` callable.
        """
        import json
        import urllib.error
        import urllib.request

        try:
            req = urllib.request.Request(
                url, headers={"Accept": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status != 200:
                    raise JwksError(
                        f"JWKS endpoint returned status {resp.status}"
                    )
                body = resp.read()
                return json.loads(body.decode("utf-8"))
        except urllib.error.URLError as e:
            raise JwksError(f"JWKS fetch failed: {e}") from e
        except (OSError, ValueError) as e:
            raise JwksError(f"JWKS fetch failed: {e}") from e

    def _fetch_jwks(self) -> dict[str, Any]:
        """Fetch the JWKS from the configured endpoint. Raises JwksError
        on network/parse failure."""
        url = self._config.resolved_jwks_url
        if not url:
            raise JwksError("JWKS URL is not configured")
        return self._http_get(url, self._config.jwks_timeout_seconds)

    def _refresh_cache(self) -> None:
        """Re-fetch the JWKS and rebuild the cache. Caller holds the lock."""
        jwks = self._fetch_jwks()
        keys = jwks.get("keys", [])
        new_cache: dict[str, Any] = {}
        for jwk in keys:
            if not isinstance(jwk, dict):
                continue
            kid = jwk.get("kid")
            kty = jwk.get("kty")
            if not kid or kty != "RSA":
                continue
            try:
                # Convert JWK → RSA public key object.
                pub = RSAAlgorithm.from_jwk(jwk)
                new_cache[kid] = pub
            except (ValueError, PyJWKClientError) as e:
                # Skip malformed JWKs but don't fail the whole cache.
                self._log.warning(
                    "oidc.jwks.malformed_key", kid=kid, error=str(e),
                )
        self._cache = new_cache
        self._cache_fetched_at = time.time()
        self._log.info("oidc.jwks.refreshed", key_count=len(new_cache))

    def _cache_expired(self) -> bool:
        """True iff the cache is older than TTL."""
        if self._cache_fetched_at == 0.0:
            return True
        age = time.time() - self._cache_fetched_at
        return age > self._config.jwks_cache_ttl_seconds

    def resolve(self, kid: str) -> Any:
        """Resolve a public key by ``kid``.

        Algorithm:
          1. If cache is empty/expired, refresh.
          2. If kid in cache, return the key.
          3. If kid NOT in cache, refresh once (key rotation event).
          4. If kid still not in cache → raise JwksError.

        Args:
            kid: The key ID from the JWT header.

        Returns:
            The RSA public key object (cryptography RSAPublicKey).

        Raises:
            JwksError: if the kid is unknown or the fetch failed.
        """
        if not kid:
            raise JwksError("kid is empty — token header missing key id")

        with self._lock:
            if self._cache_expired() or not self._cache:
                try:
                    self._refresh_cache()
                except JwksError as e:
                    # Re-raise but only after logging. Don't cache the
                    # failure — the next request will retry.
                    self._log.warning("oidc.jwks.refresh_failed", error=str(e))
                    raise

            key = self._cache.get(kid)
            if key is not None:
                return key

            # Unknown kid → try one refresh (rotation event).
            self._log.info("oidc.jwks.unknown_kid_refresh", kid=kid)
            try:
                self._refresh_cache()
            except JwksError as e:
                raise JwksError(
                    f"Unknown kid {kid!r} and JWKS refresh failed: {e}"
                ) from e

            key = self._cache.get(kid)
            if key is None:
                raise JwksError(
                    f"Unknown kid {kid!r}: not found in JWKS after refresh"
                )
            return key

    def clear_cache(self) -> None:
        """Test-only: clear the in-memory cache."""
        with self._lock:
            self._cache = {}
            self._cache_fetched_at = 0.0
