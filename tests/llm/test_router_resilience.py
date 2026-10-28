"""Tests for albra.llm.router resilience layer (HARDENING-3 Block 5).

Covers:
- CircuitBreaker state machine (CLOSED → OPEN → HALF_OPEN → CLOSED)
- LLMRouter.retry_with_fallback (Mock fallback on failure)
- LLMRouter.provider_health (per-provider status dict)
- LLMRouter.cost_estimate (Mock=0, Anthropic/OpenAI declared rates)
"""
from __future__ import annotations

import time

import pytest

from albra.llm.providers import LLMProvider, LLMResponse
from albra.llm.router import CircuitBreaker, LLMRouter

# ===== CircuitBreaker standalone =====


def test_circuit_breaker_starts_closed():
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60.0)
    assert cb.state_of("anthropic") == CircuitBreaker.CLOSED
    assert cb.can_call("anthropic") is True


def test_circuit_breaker_opens_after_threshold():
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60.0)
    for _ in range(3):
        cb.record_failure("anthropic")
    assert cb.state_of("anthropic") == CircuitBreaker.OPEN
    assert cb.can_call("anthropic") is False


def test_circuit_breaker_half_open_after_timeout():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.05)
    cb.record_failure("anthropic")
    cb.record_failure("anthropic")
    assert cb.state_of("anthropic") == CircuitBreaker.OPEN
    time.sleep(0.06)
    # First call after timeout should transition to HALF_OPEN and allow.
    assert cb.can_call("anthropic") is True
    assert cb.state_of("anthropic") == CircuitBreaker.HALF_OPEN


def test_circuit_breaker_closes_on_success():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.05)
    cb.record_failure("openai")
    cb.record_failure("openai")
    assert cb.state_of("openai") == CircuitBreaker.OPEN
    time.sleep(0.06)
    assert cb.can_call("openai") is True  # HALF_OPEN
    cb.record_success("openai")
    assert cb.state_of("openai") == CircuitBreaker.CLOSED


def test_circuit_breaker_reopens_on_half_open_failure():
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.05)
    cb.record_failure("ollama")
    assert cb.state_of("ollama") == CircuitBreaker.OPEN
    time.sleep(0.06)
    assert cb.can_call("ollama") is True  # HALF_OPEN
    cb.record_failure("ollama")  # trial failed → back to OPEN
    assert cb.state_of("ollama") == CircuitBreaker.OPEN


# ===== LLMRouter.retry_with_fallback =====


class _AlwaysFailProvider(LLMProvider):
    """Provider that always raises — used to drive fallback path."""

    name = "failtest"
    default_model = "fail-1.0"
    supports_embeddings = False

    def __init__(self, api_key: str | None = None, default_model: str | None = None) -> None:
        super().__init__(api_key, default_model)

    def generate(self, prompt, **kwargs) -> LLMResponse:
        raise RuntimeError("simulated provider outage")

    def chat(self, messages, **kwargs) -> LLMResponse:
        raise RuntimeError("simulated provider outage")

    def health_check(self) -> dict:
        return {"provider": self.name, "available": True, "model": self.default_model}


@pytest.fixture
def router_with_failing_provider() -> LLMRouter:
    router = LLMRouter(default_provider="mock")
    # Lower threshold so 2 failures trip the breaker (matches max_retries=1).
    router.breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=60.0)
    router._providers["failtest"] = _AlwaysFailProvider()
    return router


def test_retry_with_fallback_uses_mock_on_failure(router_with_failing_provider):
    router = router_with_failing_provider
    resp = router.retry_with_fallback(
        "Redacta una tutela de salud",
        preferred_provider="failtest",
        max_retries=1,
    )
    # Fallback to Mock: provider must be "mock"
    assert resp.provider == "mock"
    assert resp.text  # non-empty
    # The breaker should be OPEN after 2 failures (threshold=2).
    assert router.breaker.state_of("failtest") == CircuitBreaker.OPEN


def test_retry_with_fallback_succeeds_first_try():
    router = LLMRouter(default_provider="mock")
    resp = router.retry_with_fallback(
        "Redacta una tutela de salud",
        preferred_provider="mock",
        max_retries=2,
    )
    assert resp.provider == "mock"
    # Success recorded, breaker stays CLOSED.
    assert router.breaker.state_of("mock") == CircuitBreaker.CLOSED


def test_retry_with_fallback_breaker_open_short_circuits_to_mock(
    router_with_failing_provider,
):
    router = router_with_failing_provider
    # Trip the breaker via record_failure so can_call() returns False,
    # forcing retry_with_fallback to skip the provider entirely and
    # fall straight back to Mock.
    for _ in range(router.breaker.failure_threshold):
        router.breaker.record_failure("failtest")
    assert router.breaker.state_of("failtest") == CircuitBreaker.OPEN
    resp = router.retry_with_fallback(
        "Redacta una tutela",
        preferred_provider="failtest",
        max_retries=2,
    )
    # Should fall back to Mock immediately.
    assert resp.provider == "mock"


# ===== provider_health =====


def test_provider_health_reports_status():
    router = LLMRouter(default_provider="mock")
    health = router.provider_health()
    assert isinstance(health, dict)
    for name in ("mock", "anthropic", "openai", "ollama"):
        assert name in health
        entry = health[name]
        assert "circuit_state" in entry
        assert "available" in entry
        assert "model" in entry
        assert "supports_embeddings" in entry
        assert "health" in entry
    # Fresh router: all breakers CLOSED.
    for entry in health.values():
        assert entry["circuit_state"] == CircuitBreaker.CLOSED
    # Mock is always available.
    assert health["mock"]["available"] is True


def test_provider_health_reflects_breaker_state():
    router = LLMRouter(default_provider="mock")
    # Trip the breaker for "anthropic" so health reflects OPEN.
    for _ in range(router.breaker.failure_threshold):
        router.breaker.record_failure("anthropic")
    health = router.provider_health()
    assert health["anthropic"]["circuit_state"] == CircuitBreaker.OPEN


# ===== cost_estimate =====


def test_cost_estimate_returns_zero_for_mock():
    router = LLMRouter(default_provider="mock")
    # Mock cost = 0 regardless of token count.
    assert router.cost_estimate("mock", 0) == 0.0
    assert router.cost_estimate("mock", 1_000) == 0.0
    assert router.cost_estimate("mock", 1_000_000) == 0.0


def test_cost_estimate_returns_zero_for_ollama():
    router = LLMRouter(default_provider="mock")
    assert router.cost_estimate("ollama", 10_000) == 0.0


def test_cost_estimate_positive_for_anthropic():
    router = LLMRouter(default_provider="mock")
    cost = router.cost_estimate("anthropic", 1_000_000)
    # 1M input @ $3 + 1M output @ $15 = $18.00
    assert cost == 18.0


def test_cost_estimate_positive_for_openai():
    router = LLMRouter(default_provider="mock")
    cost = router.cost_estimate("openai", 1_000_000)
    # 1M input @ $0.15 + 1M output @ $0.60 = $0.75
    assert cost == 0.75


def test_cost_estimate_unknown_provider_returns_zero():
    router = LLMRouter(default_provider="mock")
    assert router.cost_estimate("nonexistent-provider", 10_000) == 0.0
