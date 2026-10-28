"""
LLM PROVIDERS — router de proveedores de LLM (Mock, Anthropic, OpenAI, Ollama).

V2.3-F: scaffold modular. Cada provider tiene la misma interfaz
(generate, chat, embed) para que sea intercambiable.

Inspiración: V1.0 ya tenía albra/providers/ (mock/openai/anthropic).
V2.3-F añade:
- LLMProvider abstract base class
- MockProvider (rule-based para tests, sin API key)
- AnthropicProvider (Claude 3.5 Sonnet / Opus)
- OpenAIProvider (GPT-4o / GPT-4o-mini)
- OllamaProvider (local models: llama3, mistral, qwen2)
- LLMRouter (selects provider by name + fallback chain)

Integración:
- AdversarialPipeline V2.2-C acepta llm_provider inyetable (era None = rule-based)
- DRAFTING-AGENT puede usar llm_provider para generar tutelas/demandas reales
- REVIEW-AGENT puede usar llm_provider para argumentos reales

V2.3-F default: MockProvider (rule-based, sin API key).
V2.6+: integrar con settings.ALBRA_DEFAULT_PROVIDER y keys de environment.
"""
from albra.llm.providers import (
    AnthropicProvider,
    LLMProvider,
    LLMResponse,
    MockProvider,
    OllamaProvider,
    OpenAIProvider,
)
from albra.llm.router import LLMRouter, get_default_router

__all__ = [
    "AnthropicProvider",
    "LLMProvider",
    "LLMResponse",
    "LLMRouter",
    "MockProvider",
    "OllamaProvider",
    "OpenAIProvider",
    "get_default_router",
]
