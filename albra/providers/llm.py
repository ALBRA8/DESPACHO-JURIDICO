"""Proveedores LLM - mock, OpenAI, Anthropic."""
from __future__ import annotations

from typing import Any

from albra.providers.base import Provider, ProviderResponse


class MockLLMProvider(Provider):
    """LLM de juguete - responde con plantillas. Sin deps externos."""

    name = "mock"
    kind = "llm"

    async def call(self, prompt: str, **kwargs: Any) -> ProviderResponse:
        # Respuesta simple basada en el prompt
        if "?" in prompt:
            text = (
                "[MOCK-LLM] Pregunta detectada. El proveedor real aún no está "
                "configurado. Para activar LLM real, set ALBRA_OPENAI_API_KEY "
                "o ALBRA_ANTHROPIC_API_KEY y ALBRA_DEFAULT_PROVIDER=openai|anthropic."
            )
        else:
            text = f"[MOCK-LLM] Recibido: {prompt[:80]}..."
        return ProviderResponse(ok=True, text=text, raw={"provider": "mock"})


class OpenAIProvider(Provider):
    name = "openai"
    kind = "llm"

    def __init__(self, *, api_key: str, model: str = "gpt-4o-mini") -> None:
        self.api_key = api_key
        self.model = model

    async def call(self, prompt: str, **kwargs: Any) -> ProviderResponse:
        try:
            import openai  # type: ignore[import]
        except ImportError:
            return ProviderResponse(
                ok=False, error="Paquete 'openai' no instalado. pip install openai"
            )
        try:
            client = openai.AsyncOpenAI(api_key=self.api_key)
            r = await client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                **kwargs,
            )
            text = r.choices[0].message.content or ""
            return ProviderResponse(ok=True, text=text, raw={"model": self.model})
        except Exception as e:  # noqa: BLE001
            return ProviderResponse(ok=False, error=str(e))


class AnthropicProvider(Provider):
    name = "anthropic"
    kind = "llm"

    def __init__(self, *, api_key: str, model: str = "claude-3-5-sonnet-20241022") -> None:
        self.api_key = api_key
        self.model = model

    async def call(self, prompt: str, **kwargs: Any) -> ProviderResponse:
        try:
            import anthropic  # type: ignore[import]
        except ImportError:
            return ProviderResponse(
                ok=False, error="Paquete 'anthropic' no instalado. pip install anthropic"
            )
        try:
            client = anthropic.AsyncAnthropic(api_key=self.api_key)
            r = await client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            text = r.content[0].text if r.content else ""
            return ProviderResponse(ok=True, text=text, raw={"model": self.model})
        except Exception as e:  # noqa: BLE001
            return ProviderResponse(ok=False, error=str(e))
