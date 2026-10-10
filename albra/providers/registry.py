"""Registry de providers - LLM, search, TTS, etc."""
from __future__ import annotations

from albra.config.settings import Settings
from albra.observability.logger import get_logger
from albra.providers.base import Provider


class ProviderRegistry:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.log = get_logger("albra.providers")
        self._providers: dict[str, Provider] = {}

        # Auto-registro de providers según settings
        from albra.providers.llm import AnthropicProvider, MockLLMProvider, OpenAIProvider
        self.register("mock", MockLLMProvider())
        if settings.openai_api_key:
            self.register("openai", OpenAIProvider(api_key=settings.openai_api_key))
        if settings.anthropic_api_key:
            self.register("anthropic", AnthropicProvider(api_key=settings.anthropic_api_key))

    def register(self, name: str, provider: Provider) -> None:
        self._providers[name] = provider
        self.log.info("providers.registered", name=name, kind=provider.kind)

    def get(self, name: str | None = None) -> Provider:
        name = name or self.settings.default_provider
        if name not in self._providers:
            # Fallback a mock - el default explícito
            return self._providers["mock"]
        return self._providers[name]

    def list(self) -> list[str]:
        return list(self._providers.keys())

    async def startup(self) -> None:
        for p in self._providers.values():
            await p.startup()
        self.log.info("providers.startup", registered=list(self._providers.keys()))

    async def shutdown(self) -> None:
        for p in self._providers.values():
            await p.shutdown()
