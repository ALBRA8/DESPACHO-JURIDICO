"""
LLM ROUTER — selecciona provider por nombre + fallback chain.

V2.3-F: router simple que intenta el provider preferido y cae al
Mock si falla (Mock siempre funciona).

Uso:
    router = get_default_router()
    response = router.generate("Redacta una tutela de salud")

    # Override provider
    response = router.generate("...", preferred_provider="anthropic")

Settings:
- ALBRA_LLM_DEFAULT_PROVIDER env var (default: 'mock')
- Si provider preferido no está disponible (no API key, no host),
  fallback automático a Mock.
"""
from __future__ import annotations

import os
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


class LLMRouter:
    """Router de LLM providers con fallback."""

    def __init__(self, default_provider: str = "mock") -> None:
        self.default_provider = default_provider
        self.log = get_logger("albra.llm.router")
        self._providers: dict[str, LLMProvider] = {}
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
