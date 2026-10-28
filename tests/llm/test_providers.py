"""Tests del módulo LLM (providers + router)."""
from __future__ import annotations

import os

import pytest

from albra.llm.providers import (
    AnthropicProvider,
    LLMProvider,
    LLMResponse,
    MockProvider,
    OllamaProvider,
    OpenAIProvider,
)
from albra.llm.router import LLMRouter, get_default_router, reset_router

# ===== MockProvider =====

@pytest.fixture
def mock():
    return MockProvider()


def test_mock_provider_init_no_api_key(mock):
    assert mock.name == "mock"
    assert mock.default_model == "mock-1.0"
    assert mock.api_key is None


def test_mock_generate_returns_llm_response(mock):
    r = mock.generate("Hola")
    assert isinstance(r, LLMResponse)
    assert r.provider == "mock"
    assert r.text
    assert r.tokens_in > 0
    assert r.tokens_out > 0
    assert r.usd_cost == 0.0  # mock = free


def test_mock_generate_tutela_salud(mock):
    r = mock.generate("Redacta una tutela de salud")
    assert "ACCION DE TUTELA" in r.text
    assert "salud" in r.text.lower() or "49" in r.text  # art 49 Constitución
    assert "Disclaimer" in r.text  # always include disclaimer


def test_mock_generate_demanda_civil(mock):
    r = mock.generate("Demanda civil")
    assert "DEMANDA CIVIL" in r.text
    assert "2341" in r.text  # Código Civil article


def test_mock_generate_contrato_corporativo(mock):
    r = mock.generate("Contrato corporativo")
    assert "CONTRATO CORPORATIVO" in r.text
    assert "Cláusula" in r.text


def test_mock_generate_adversarial(mock):
    r = mock.generate("Genera contra-argumento para red team")
    assert "RED phase" in r.text or "BLUE phase" in r.text


def test_mock_chat_uses_last_user_message(mock):
    messages = [
        {"role": "system", "content": "You are a legal AI"},
        {"role": "user", "content": "Redacta una tutela de salud"},
    ]
    r = mock.chat(messages)
    assert "ACCION DE TUTELA" in r.text


def test_mock_health_check_always_available(mock):
    h = mock.health_check()
    assert h["provider"] == "mock"
    assert h["available"] is True
    assert h["api_key_required"] is False


def test_mock_response_as_dict(mock):
    r = mock.generate("test")
    d = r.as_dict()
    assert d["text"] == r.text
    assert d["provider"] == "mock"
    assert "tokens_in" in d
    assert "metadata" in d


# ===== AnthropicProvider (scaffold) =====

def test_anthropic_provider_init_no_api_key_warns(caplog):
    import logging
    with caplog.at_level(logging.WARNING, logger="albra.llm.anthropic"):
        p = AnthropicProvider()
    assert p.name == "anthropic"
    assert p.api_key is None
    assert any("no_api_key" in r.message for r in caplog.records)


def test_anthropic_provider_init_with_api_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-123456789")
    p = AnthropicProvider()
    assert p.api_key == "sk-ant-test-123456789"
    assert p.default_model == "claude-3-5-sonnet-20241022"


def test_anthropic_generate_without_api_key_falls_back_to_mock(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    p = AnthropicProvider()
    r = p.generate("Redacta una tutela")
    assert r.provider == "mock"  # fell back


def test_anthropic_generate_with_api_key_raises_not_implemented(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-123456789")
    p = AnthropicProvider()
    with pytest.raises(NotImplementedError, match="V2.6"):
        p.generate("test")


def test_anthropic_health_check_reports_status(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    p = AnthropicProvider()
    h = p.health_check()
    assert h["provider"] == "anthropic"
    assert h["available"] is False
    assert h["api_key_required"] is True
    assert "v2_6_pending" in h


# ===== OpenAIProvider (scaffold) =====

def test_openai_provider_init(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    p = OpenAIProvider()
    assert p.name == "openai"
    assert p.default_model == "gpt-4o-mini"
    assert p.supports_embeddings is True
    assert p.api_key is None


def test_openai_provider_init_with_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-123456789")
    p = OpenAIProvider()
    assert p.api_key == "sk-test-123456789"


def test_openai_embed_without_key_returns_mock(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    p = OpenAIProvider()
    emb = p.embed("test text")
    assert isinstance(emb, list)
    assert len(emb) == 32  # mock embedding
    assert all(0 <= v <= 1 for v in emb)


def test_openai_embed_deterministic(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    p = OpenAIProvider()
    e1 = p.embed("test text")
    e2 = p.embed("test text")
    assert e1 == e2  # same input → same embedding


def test_openai_health_check(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    p = OpenAIProvider()
    h = p.health_check()
    assert h["provider"] == "openai"
    assert h["available"] is False
    assert h["supports_embeddings"] is True


# ===== OllamaProvider (scaffold) =====

def test_ollama_provider_init_default_host():
    p = OllamaProvider()
    assert p.name == "ollama"
    assert p.host == "http://localhost:11434"
    assert p.default_model == "llama3"
    assert p.supports_embeddings is True


def test_ollama_provider_init_custom_host(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://ollama-host:11434")
    p = OllamaProvider()
    assert p.host == "http://ollama-host:11434"


def test_ollama_health_check_returns_dict():
    p = OllamaProvider()
    h = p.health_check()
    assert h["provider"] == "ollama"
    assert "available" in h
    assert "host" in h
    # Likely unavailable in test env (no ollama running)
    assert h["available"] is False or h["available"] is True


def test_ollama_embed_falls_back_to_mock_if_unavailable():
    p = OllamaProvider()
    emb = p.embed("test text")
    # Even if Ollama unavailable, should return mock embedding
    assert isinstance(emb, list)
    assert len(emb) == 32


# ===== LLMRouter =====

@pytest.fixture
def router():
    reset_router()
    return LLMRouter(default_provider="mock")


def test_router_init_creates_all_providers(router):
    assert router.default_provider == "mock"
    assert set(router._providers.keys()) == {"mock", "anthropic", "openai", "ollama"}


def test_router_get_provider_returns_default(router):
    p = router.get_provider()
    assert p.name == "mock"


def test_router_get_provider_by_name(router):
    p = router.get_provider("anthropic")
    assert p.name == "anthropic"


def test_router_get_unknown_provider_falls_back_to_mock(router):
    p = router.get_provider("nonexistent")
    assert p.name == "mock"


def test_router_generate_uses_default(router):
    r = router.generate("Redacta tutela de salud")
    assert r.provider == "mock"
    assert "ACCION DE TUTELA" in r.text


def test_router_generate_with_preferred_provider_falls_back_to_mock(router):
    # Anthropic without API key should fall back to mock
    r = router.generate("test", preferred_provider="anthropic")
    assert r.provider == "mock"  # fell back


def test_router_chat_uses_default(router):
    messages = [{"role": "user", "content": "Demanda civil"}]
    r = router.chat(messages)
    assert r.provider == "mock"
    assert "DEMANDA CIVIL" in r.text


def test_router_list_providers(router):
    providers = router.list_providers()
    assert len(providers) == 4
    names = [p["name"] for p in providers]
    assert "mock" in names
    assert "anthropic" in names
    assert "openai" in names
    assert "ollama" in names


def test_router_stats(router):
    stats = router.stats()
    assert stats["default_provider"] == "mock"
    assert "providers" in stats
    assert "available_providers" in stats
    # Mock should always be available
    assert "mock" in stats["available_providers"]


# ===== Singleton =====

def test_get_default_router_returns_singleton():
    reset_router()
    r1 = get_default_router()
    r2 = get_default_router()
    assert r1 is r2


def test_get_default_router_uses_env_var(monkeypatch):
    monkeypatch.setenv("ALBRA_LLM_DEFAULT_PROVIDER", "anthropic")
    reset_router()
    r = get_default_router()
    assert r.default_provider == "anthropic"


def test_reset_router_clears_singleton():
    r1 = get_default_router()
    reset_router()
    r2 = get_default_router()
    assert r1 is not r2
