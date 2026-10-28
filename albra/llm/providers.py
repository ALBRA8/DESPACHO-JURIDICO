"""
LLM PROVIDERS — implementations.

Cada provider implementa la interfaz LLMProvider:
- generate(prompt: str, **kwargs) -> LLMResponse
- chat(messages: list[dict], **kwargs) -> LLMResponse
- embed(text: str) -> list[float] (solo si soporta embeddings)

V2.3-F default: MockProvider (sin API key, rule-based).
Otros providers requieren API key en environment:
- ANTHROPIC_API_KEY para AnthropicProvider
- OPENAI_API_KEY para OpenAIProvider
- OLLAMA_HOST (default http://localhost:11434) para OllamaProvider
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any

from albra.observability.logger import get_logger


@dataclass
class LLMResponse:
    """Respuesta estandarizada de cualquier provider LLM."""
    text: str
    provider: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    usd_cost: float = 0.0
    latency_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "provider": self.provider,
            "model": self.model,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "usd_cost": self.usd_cost,
            "latency_ms": self.latency_ms,
            "metadata": self.metadata,
        }


class LLMProvider:
    """Abstract base class para todos los LLM providers."""

    name: str = "abstract"
    default_model: str = ""
    supports_embeddings: bool = False

    def __init__(self, api_key: str | None = None, default_model: str | None = None) -> None:
        self.api_key = api_key
        self.default_model = default_model or self.default_model
        self.log = get_logger(f"albra.llm.{self.name}")

    def generate(self, prompt: str, *, model: str | None = None, max_tokens: int = 1000, temperature: float = 0.7, **kwargs) -> LLMResponse:
        """Genera texto a partir de un prompt."""
        raise NotImplementedError

    def chat(self, messages: list[dict[str, str]], *, model: str | None = None, max_tokens: int = 1000, temperature: float = 0.7, **kwargs) -> LLMResponse:
        """Chat con messages [{role, content}]."""
        raise NotImplementedError

    def embed(self, text: str, *, model: str | None = None) -> list[float]:
        """Embeddings (solo si supports_embeddings=True)."""
        raise NotImplementedError(f"{self.name} does not support embeddings")

    def health_check(self) -> dict[str, Any]:
        """Verifica que el provider esté disponible."""
        raise NotImplementedError


class MockProvider(LLMProvider):
    """Provider mock para tests y demos sin API key.

    Reglas de generación:
    - Detecta keywords en el prompt y genera respuesta rule-based.
    - Simula latency (10-50ms).
    - Simula tokens (1 token ≈ 4 chars).
    - Costo: 0.0 (es mock).
    """

    name = "mock"
    default_model = "mock-1.0"
    supports_embeddings = False

    def __init__(self, api_key: str | None = None, default_model: str | None = None) -> None:
        super().__init__(api_key, default_model)
        # Mock no requiere API key

    def generate(self, prompt: str, *, model: str | None = None, max_tokens: int = 1000, temperature: float = 0.7, **kwargs) -> LLMResponse:
        start = time.time()
        text = self._generate_mock(prompt)
        elapsed_ms = (time.time() - start) * 1000
        return LLMResponse(
            text=text,
            provider=self.name,
            model=model or self.default_model,
            tokens_in=len(prompt) // 4,
            tokens_out=len(text) // 4,
            usd_cost=0.0,
            latency_ms=elapsed_ms,
            metadata={"rule_based": True},
        )

    def chat(self, messages: list[dict[str, str]], *, model: str | None = None, max_tokens: int = 1000, temperature: float = 0.7, **kwargs) -> LLMResponse:
        # Último mensaje del user
        user_msg = next((m for m in reversed(messages) if m["role"] == "user"), None)
        prompt = user_msg["content"] if user_msg else ""
        return self.generate(prompt, model=model, max_tokens=max_tokens, temperature=temperature)

    def health_check(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "available": True,
            "model": self.default_model,
            "api_key_required": False,
        }

    def _generate_mock(self, prompt: str) -> str:
        """Rule-based response generation."""
        p = prompt.lower()
        if "tutela" in p and "salud" in p:
            return (
                "ACCION DE TUTELA\n\n"
                "El peticionario solicita la protección del derecho fundamental a la salud, "
                "amparado por el artículo 49 de la Constitución Política de 1991. La EPS "
                "ha negado el medicamento formulado, lo cual constituye una vulneración "
                "manifiesta. Se solicita al juez constitucional tutelar el derecho y ordenar "
                "la entrega inmediata del medicamento.\n\n"
                "Disclaimer: Borrador generado por ALBRA MockProvider (rule-based). "
                "Requiere revisión y firma de abogado calificado."
            )
        if "demanda" in p and "civil" in p:
            return (
                "DEMANDA CIVIL\n\n"
                "Por medio de la presente demanda civil, el actor solicita al juzgado "
                "competente la declaración de responsabilidad civil extracontractual del "
                "demandado, con base en el artículo 2341 del Código Civil. Se reclama "
                "indemnización por los perjuicios causados.\n\n"
                "Disclaimer: Borrador generado por ALBRA MockProvider (rule-based)."
            )
        if "contrato" in p and "corporativo" in p:
            return (
                "CONTRATO CORPORATIVO\n\n"
                "Cláusula 1 (Objeto): El presente contrato tiene por objeto...\n"
                "Cláusula 2 (Precio): El precio total es de...\n"
                "Cláusula 3 (Plazo): La vigencia del contrato será de...\n"
                "Cláusula 4 (Jurisdicción): Las partes se someten a la jurisdicción de...\n\n"
                "Disclaimer: Borrador generado por ALBRA MockProvider (rule-based)."
            )
        if "argumento" in p or "red team" in p or "contra" in p:
            return (
                "Contra-argumento (RED phase):\n"
                "1. La pretensión no cita norma específica del corpus V1.1.\n"
                "2. No se considera la jurisprudencia contradictoria potencial.\n"
                "3. Falta evidencia documental de los hechos alegados.\n"
                "4. La cuantía podría exceder el límite de la jurisdicción municipal.\n\n"
                "Defense (BLUE phase):\n"
                "1. La norma aplicable es Constitución art. 13 (igualdad).\n"
                "2. La jurisprudencia de la Corte Constitucional apoya la pretensión.\n"
                "3. La evidencia documental se presentará en el expediente.\n"
                "4. La cuantía se ajusta a la jurisdicción competente."
            )
        # Default
        return (
            f"[Mock response to: {prompt[:200]}]\n\n"
            "This is a rule-based mock response. Configure ANTHROPIC_API_KEY or "
            "OPENAI_API_KEY for real LLM generation."
        )


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider (Claude 3.5 Sonnet, Opus, Haiku).

    Requiere: ANTHROPIC_API_KEY en environment.

    V2.3-F: scaffold. No hace HTTP real si no hay API key (delegado a
    V2.6+ cuando se integre el SDK de anthropic).
    """

    name = "anthropic"
    default_model = "claude-3-5-sonnet-20241022"
    supports_embeddings = False

    def __init__(self, api_key: str | None = None, default_model: str | None = None) -> None:
        api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        super().__init__(api_key, default_model)
        if not self.api_key:
            self.log.warning("anthropic.no_api_key", reason="ANTHROPIC_API_KEY not set; will fallback to Mock")

    def generate(self, prompt: str, *, model: str | None = None, max_tokens: int = 1000, temperature: float = 0.7, **kwargs) -> LLMResponse:
        if not self.api_key:
            # Fallback a mock si no hay key
            return MockProvider().generate(prompt, model=model, max_tokens=max_tokens, temperature=temperature)
        # V2.6+: integrar anthropic SDK real
        # import anthropic
        # client = anthropic.Anthropic(api_key=self.api_key)
        # message = client.messages.create(model=model or self.default_model, max_tokens=max_tokens, temperature=temperature, messages=[{"role": "user", "content": prompt}])
        # return LLMResponse(text=message.content[0].text, provider=self.name, model=...)
        raise NotImplementedError(
            "Anthropic SDK integration pending V2.6+. Set ANTHROPIC_API_KEY and "
            "install anthropic package, or use MockProvider for testing."
        )

    def chat(self, messages: list[dict[str, str]], *, model: str | None = None, max_tokens: int = 1000, temperature: float = 0.7, **kwargs) -> LLMResponse:
        if not self.api_key:
            return MockProvider().chat(messages, model=model, max_tokens=max_tokens, temperature=temperature)
        raise NotImplementedError("Anthropic SDK integration pending V2.6+")

    def health_check(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "available": bool(self.api_key),
            "model": self.default_model,
            "api_key_required": True,
            "api_key_set": bool(self.api_key),
            "v2_6_pending": "Real HTTP integration with anthropic SDK",
        }


class OpenAIProvider(LLMProvider):
    """OpenAI GPT-4o provider.

    Requiere: OPENAI_API_KEY en environment.
    """

    name = "openai"
    default_model = "gpt-4o-mini"
    supports_embeddings = True

    def __init__(self, api_key: str | None = None, default_model: str | None = None) -> None:
        api_key = api_key or os.environ.get("OPENAI_API_KEY")
        super().__init__(api_key, default_model)
        if not self.api_key:
            self.log.warning("openai.no_api_key", reason="OPENAI_API_KEY not set; will fallback to Mock")

    def generate(self, prompt: str, *, model: str | None = None, max_tokens: int = 1000, temperature: float = 0.7, **kwargs) -> LLMResponse:
        if not self.api_key:
            return MockProvider().generate(prompt, model=model, max_tokens=max_tokens, temperature=temperature)
        # V2.6+: from openai import OpenAI; client = OpenAI(api_key=self.api_key)
        raise NotImplementedError("OpenAI SDK integration pending V2.6+")

    def chat(self, messages: list[dict[str, str]], *, model: str | None = None, max_tokens: int = 1000, temperature: float = 0.7, **kwargs) -> LLMResponse:
        if not self.api_key:
            return MockProvider().chat(messages, model=model, max_tokens=max_tokens, temperature=temperature)
        raise NotImplementedError("OpenAI SDK integration pending V2.6+")

    def embed(self, text: str, *, model: str | None = None) -> list[float]:
        if not self.api_key:
            # Mock embedding: hash-based deterministic
            import hashlib
            h = hashlib.sha256(text.encode()).digest()
            # Convert to 32 floats (0..1)
            return [b / 255 for b in h[:32]]
        raise NotImplementedError("OpenAI SDK integration pending V2.6+")

    def health_check(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "available": bool(self.api_key),
            "model": self.default_model,
            "api_key_required": True,
            "api_key_set": bool(self.api_key),
            "supports_embeddings": True,
            "v2_6_pending": "Real HTTP integration with openai SDK",
        }


class OllamaProvider(LLMProvider):
    """Ollama local provider (llama3, mistral, qwen2, phi3, etc.).

    Requiere: Ollama running on http://localhost:11434 (or OLLAMA_HOST).
    No requiere API key (es local).
    """

    name = "ollama"
    default_model = "llama3"
    supports_embeddings = True

    def __init__(self, api_key: str | None = None, default_model: str | None = None) -> None:
        # Ollama doesn't need API key, just host
        self.host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        super().__init__(api_key, default_model)

    def generate(self, prompt: str, *, model: str | None = None, max_tokens: int = 1000, temperature: float = 0.7, **kwargs) -> LLMResponse:
        # V2.6+: import requests; r = requests.post(f"{self.host}/api/generate", json={"model": model or self.default_model, "prompt": prompt, "stream": False})
        # Try real HTTP if requests available
        try:
            import requests
            r = requests.post(
                f"{self.host}/api/generate",
                json={
                    "model": model or self.default_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": temperature, "num_predict": max_tokens},
                },
                timeout=30,
            )
            if r.status_code == 200:
                data = r.json()
                return LLMResponse(
                    text=data.get("response", ""),
                    provider=self.name,
                    model=model or self.default_model,
                    tokens_in=data.get("prompt_eval_count", 0),
                    tokens_out=data.get("eval_count", 0),
                    usd_cost=0.0,  # Local = free
                    latency_ms=data.get("total_duration", 0) / 1_000_000,  # nanos to ms
                )
            return MockProvider().generate(prompt, model=model)
        except Exception as e:
            self.log.warning("ollama.unavailable", host=self.host, error=str(e))
            return MockProvider().generate(prompt, model=model)

    def chat(self, messages: list[dict[str, str]], *, model: str | None = None, max_tokens: int = 1000, temperature: float = 0.7, **kwargs) -> LLMResponse:
        try:
            import requests
            r = requests.post(
                f"{self.host}/api/chat",
                json={
                    "model": model or self.default_model,
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": temperature, "num_predict": max_tokens},
                },
                timeout=30,
            )
            if r.status_code == 200:
                data = r.json()
                return LLMResponse(
                    text=data.get("message", {}).get("content", ""),
                    provider=self.name,
                    model=model or self.default_model,
                    tokens_in=data.get("prompt_eval_count", 0),
                    tokens_out=data.get("eval_count", 0),
                    usd_cost=0.0,
                    latency_ms=data.get("total_duration", 0) / 1_000_000,
                )
            return MockProvider().chat(messages, model=model)
        except Exception as e:
            self.log.warning("ollama.unavailable", host=self.host, error=str(e))
            return MockProvider().chat(messages, model=model)

    def embed(self, text: str, *, model: str | None = None) -> list[float]:
        try:
            import requests
            r = requests.post(
                f"{self.host}/api/embeddings",
                json={"model": model or "nomic-embed-text", "prompt": text},
                timeout=30,
            )
            if r.status_code == 200:
                return r.json().get("embedding", [])
        except Exception as e:
            self.log.warning("ollama.embed_unavailable", error=str(e))
        # Fallback: mock embedding
        import hashlib
        h = hashlib.sha256(text.encode()).digest()
        return [b / 255 for b in h[:32]]

    def health_check(self) -> dict[str, Any]:
        try:
            import requests
            r = requests.get(f"{self.host}/api/tags", timeout=5)
            available = r.status_code == 200
            models = r.json().get("models", []) if available else []
            return {
                "provider": self.name,
                "available": available,
                "host": self.host,
                "models_installed": [m.get("name") for m in models],
                "api_key_required": False,
            }
        except Exception as e:
            return {
                "provider": self.name,
                "available": False,
                "host": self.host,
                "error": str(e),
                "api_key_required": False,
            }
