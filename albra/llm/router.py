"""
LLM ROUTER — selecciona provider por nombre + fallback chain.

V2.3-F: router simple que intenta el provider preferido y cae al
Mock si falla (Mock siempre funciona).

V2.5-H3: resilience layer (CircuitBreaker + retry_with_fallback +
provider_health + cost_estimate) so a single failing provider never
cascades — the router records the failure, opens the breaker after N
consecutive failures, half-opens after a recovery timeout, and always
has the Mock as last-resort fallback so the agent never returns an empty
response.

Uso:
    router = get_default_router()
    response = router.generate("Redacta una tutela de salud")

    # Override provider
    response = router.generate("...", preferred_provider="anthropic")

    # Resilient retry with fallback
    response = router.retry_with_fallback(
        "Redacta una tutela de salud",
        preferred_provider="anthropic",
        max_retries=2,
    )

Settings:
- ALBRA_LLM_DEFAULT_PROVIDER env var (default: 'mock')
- Si provider preferido no está disponible (no API key, no host),
  fallback automático a Mock.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

from albra.llm.providers import (
    AnthropicProvider,
    LLMProvider,
    LLMResponse,
    MockProvider,
    OllamaProvider,
    OpenAIProvider,
)
from albra.observability.logger import get_logger

_PROVIDER_CLASSES: dict[str, type[LLMProvider]] = {
    "mock": MockProvider,
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "ollama": OllamaProvider,
}

# Cost per 1M tokens (input + output) declared as metadata. Mock and
# local Ollama are free; Anthropic and OpenAI reflect list pricing at
# time of writing (V2.5). cost_estimate() multiplies these by tokens
# but the values are NEVER used to bill a real client — they exist so
# the agent can surface a "this draft cost ~$0.012" estimate.
_PROVIDER_COSTS_PER_MTOK: dict[str, dict[str, float]] = {
    "mock": {"input": 0.0, "output": 0.0},
    "ollama": {"input": 0.0, "output": 0.0},
    "anthropic": {"input": 3.0, "output": 15.0},  # claude-3-5-sonnet
    "openai": {"input": 0.15, "output": 0.60},   # gpt-4o-mini
}


@dataclass
class _BreakerState:
    """Mutable per-provider breaker state."""

    state: str = "CLOSED"  # CLOSED | OPEN | HALF_OPEN
    failure_count: int = 0
    success_count: int = 0
    opened_at: float = 0.0
    last_failure: float = 0.0


class CircuitBreaker:
    """LLM provider circuit breaker (router-scoped).

    Tracks consecutive failures per provider. Opens after N failures
    (default 3), half-opens after a recovery timeout, closes on the
    first success observed in half-open.

    States:
    - CLOSED: normal flow, all calls pass.
    - OPEN: blocks all calls to this provider until recovery_timeout
      elapses, then transitions to HALF_OPEN.
    - HALF_OPEN: allows a trial call; success -> CLOSED, failure ->
      back to OPEN.
    """

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

    def __init__(
        self,
        *,
        failure_threshold: int = 3,
        recovery_timeout: float = 60.0,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._states: dict[str, _BreakerState] = {}
        self.log = get_logger("albra.llm.circuit_breaker")

    def _get(self, provider: str) -> _BreakerState:
        if provider not in self._states:
            self._states[provider] = _BreakerState()
        return self._states[provider]

    def record_success(self, provider: str) -> None:
        s = self._get(provider)
        s.success_count += 1
        if s.state == self.HALF_OPEN:
            s.state = self.CLOSED
            s.failure_count = 0
            self.log.info("cb.closed_after_recovery", provider=provider)

    def record_failure(self, provider: str) -> None:
        s = self._get(provider)
        s.failure_count += 1
        s.last_failure = time.time()
        if s.state == self.HALF_OPEN:
            # Half-open trial failed → back to OPEN
            s.state = self.OPEN
            s.opened_at = time.time()
            self.log.warning("cb.reopened", provider=provider)
        elif s.state == self.CLOSED:
            if s.failure_count >= self.failure_threshold:
                s.state = self.OPEN
                s.opened_at = time.time()
                self.log.warning(
                    "cb.opened",
                    provider=provider,
                    failures=s.failure_count,
                )

    def can_call(self, provider: str) -> bool:
        s = self._get(provider)
        if s.state == self.CLOSED:
            return True
        if s.state == self.OPEN:
            if time.time() - s.opened_at >= self.recovery_timeout:
                s.state = self.HALF_OPEN
                self.log.info("cb.half_open", provider=provider)
                return True
            return False
        # HALF_OPEN: allow one trial call
        return True

    def state_of(self, provider: str) -> str:
        """Return the current breaker state for a provider (defaults CLOSED)."""
        return self._get(provider).state

    def status(self) -> dict[str, Any]:
        return {
            name: {
                "state": s.state,
                "failure_count": s.failure_count,
                "success_count": s.success_count,
                "opened_at": s.opened_at,
                "last_failure": s.last_failure,
            }
            for name, s in self._states.items()
        }


class LLMRouter:
    """Router de LLM providers con fallback."""

    def __init__(self, default_provider: str = "mock") -> None:
        self.default_provider = default_provider
        self.log = get_logger("albra.llm.router")
        self._providers: dict[str, LLMProvider] = {}
        self.breaker = CircuitBreaker()
        self._init_providers()

    def _init_providers(self) -> None:
        # Inicializa todos los providers (lazy: solo cargan API keys si disponibles)
        self._providers = {
            name: cls() for name, cls in _PROVIDER_CLASSES.items()
        }

    def get_provider(self, name: str | None = None) -> LLMProvider:
        """Devuelve provider por nombre. Si no existe o no disponible,
        fallback a Mock."""
        target = name or self.default_provider
        provider = self._providers.get(target)
        if not provider:
            self.log.warning("llm.unknown_provider", requested=target, fallback="mock")
            return self._providers["mock"]
        return provider

    def generate(self, prompt: str, *, preferred_provider: str | None = None, **kwargs) -> LLMResponse:
        """Genera respuesta. Si provider preferido falla, fallback a Mock."""
        provider = self.get_provider(preferred_provider)
        try:
            return provider.generate(prompt, **kwargs)
        except NotImplementedError as e:
            self.log.warning(
                "llm.fallback_to_mock",
                provider=provider.name, reason=str(e)[:100],
            )
            return self._providers["mock"].generate(prompt, **kwargs)
        except Exception as e:
            self.log.error("llm.generate_failed", provider=provider.name, error=str(e))
            return self._providers["mock"].generate(prompt, **kwargs)

    def chat(self, messages: list[dict[str, str]], *, preferred_provider: str | None = None, **kwargs) -> LLMResponse:
        provider = self.get_provider(preferred_provider)
        try:
            return provider.chat(messages, **kwargs)
        except (NotImplementedError, Exception) as e:
            self.log.warning("llm.chat_fallback_to_mock", provider=provider.name, error=str(e))
            return self._providers["mock"].chat(messages, **kwargs)

    def list_providers(self) -> list[dict[str, Any]]:
        """Lista todos los providers con su estado de salud."""
        result = []
        for name, provider in self._providers.items():
            try:
                health = provider.health_check()
                result.append({
                    "name": name,
                    "default_model": provider.default_model,
                    "supports_embeddings": provider.supports_embeddings,
                    **health,
                })
            except Exception as e:
                result.append({
                    "name": name,
                    "default_model": provider.default_model,
                    "supports_embeddings": provider.supports_embeddings,
                    "error": str(e),
                })
        return result

    def stats(self) -> dict[str, Any]:
        return {
            "default_provider": self.default_provider,
            "providers": self.list_providers(),
            "available_providers": [
                p["name"] for p in self.list_providers() if p.get("available")
            ],
        }

    # ===== V2.5-H3 resilience layer =====

    def retry_with_fallback(
        self,
        prompt: str,
        preferred_provider: str | None = None,
        max_retries: int = 2,
        **kwargs: Any,
    ) -> LLMResponse:
        """Try preferred provider; on failure, record + fall back to Mock.

        Flow:
        1. If the breaker for `preferred_provider` is OPEN (and not yet
           past recovery_timeout), short-circuit to Mock.
        2. Otherwise, attempt the call up to `max_retries + 1` times.
        3. On each failure: record_failure(provider). Once the breaker
           opens, stop retrying that provider.
        4. If all attempts fail OR the breaker is open, fall back to Mock
           (Mock always succeeds).
        """
        target = preferred_provider or self.default_provider
        attempts = 0
        last_error: Exception | None = None

        while attempts <= max_retries:
            if not self.breaker.can_call(target):
                self.log.warning(
                    "router.breaker_open", provider=target, attempt=attempts
                )
                break
            provider = self._providers.get(target)
            if provider is None:
                self.log.warning("router.unknown_provider", provider=target)
                break
            try:
                resp = provider.generate(prompt, **kwargs)
                self.breaker.record_success(target)
                return resp
            except Exception as e:  # noqa: BLE001 — every provider failure is recoverable
                last_error = e
                self.breaker.record_failure(target)
                self.log.warning(
                    "router.provider_failed",
                    provider=target,
                    attempt=attempts,
                    error=str(e)[:120],
                )
                attempts += 1

        # All retries exhausted OR breaker open → fallback to Mock.
        self.log.warning(
            "router.fallback_to_mock",
            preferred=target,
            attempts=attempts,
            error=str(last_error)[:120] if last_error else "breaker_open",
        )
        try:
            mock_resp = self._providers["mock"].generate(prompt, **kwargs)
            self.breaker.record_success("mock")
            return mock_resp
        except Exception as e:  # noqa: BLE001 — Mock failing is catastrophic; surface stub
            self.log.error("router.mock_failed", error=str(e))
            return LLMResponse(
                text="[ALBRA fallback stub: all LLM providers unavailable]",
                provider="mock",
                model="fallback-stub",
                metadata={"fallback": True, "reason": str(e)[:100]},
            )

    def provider_health(self) -> dict[str, dict[str, Any]]:
        """Per-provider health: circuit breaker state + provider availability."""
        result: dict[str, dict[str, Any]] = {}
        for name, provider in self._providers.items():
            breaker_state = self.breaker.state_of(name)
            try:
                health = provider.health_check()
            except Exception as e:  # noqa: BLE001 — health check itself may fail
                health = {"available": False, "error": str(e)}
            result[name] = {
                "circuit_state": breaker_state,
                "available": bool(health.get("available", False)),
                "model": provider.default_model,
                "supports_embeddings": provider.supports_embeddings,
                "health": health,
            }
        return result

    def cost_estimate(self, provider: str, prompt_tokens: int) -> float:
        """Estimate USD cost for `prompt_tokens` on `provider`.

        Assumes 1:1 input:output tokens as a rough approximation. Mock
        and local Ollama return 0.0 (free). Anthropic/OpenAI use list
        pricing declared in `_PROVIDER_COSTS_PER_MTOK` — declared for
        metadata only, not used to bill any client.
        """
        rates = _PROVIDER_COSTS_PER_MTOK.get(
            provider, {"input": 0.0, "output": 0.0}
        )
        input_cost = (prompt_tokens / 1_000_000.0) * rates["input"]
        output_cost = (prompt_tokens / 1_000_000.0) * rates["output"]
        return round(input_cost + output_cost, 6)


# Singleton
_router: LLMRouter | None = None


def get_default_router() -> LLMRouter:
    """Devuelve el router singleton. Default provider desde env var."""
    global _router
    if _router is None:
        default = os.environ.get("ALBRA_LLM_DEFAULT_PROVIDER", "mock")
        _router = LLMRouter(default_provider=default)
    return _router


def reset_router() -> None:
    """Para tests."""
    global _router
    _router = None
