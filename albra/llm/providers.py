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
- NVIDIA_API_KEY para NVIDIAProvider (V7.0)

V7.0 — distinción Mock/Real:
    Cada provider expone ``is_mock`` y ``is_external`` (clase attrs) para
    que el flujo de aceptación del abogado pueda distinguir:

      - is_mock=True        → respuesta rule-based/sintética. NO es análisis
                              jurídico real. Apto para tests y demos, NO
                              para aceptación jurídica.
      - is_external=True    → el provider hace HTTP a un servicio externo
                              (NVIDIA NIM, Anthropic, OpenAI, Ollama remoto).
                              Puede fallar; nunca debe caer silenciosamente
                              a Mock en el flujo de aceptación.
      - is_mock=False, is_external=False → no implementado / scaffold.

    El ``RealProviderGuard`` (albra.llm.real_provider_guard) rechaza
    caer silenciosamente a Mock cuando el flujo de aceptación exige
    un provider real.
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
    """Abstract base class para todos los LLM providers.

    V7.0: las flags ``is_mock`` e ``is_external`` permiten distinguir
    entre respuesta sintética y respuesta real de un proveedor externo.
    """

    name: str = "abstract"
    default_model: str = ""
    supports_embeddings: bool = False
    # V7.0 — flags for Mock/Real distinction.
    is_mock: bool = False        # True for rule-based / synthetic responses.
    is_external: bool = False    # True for providers that make real HTTP calls.

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

    V7.0: ``is_mock=True`` explícito. El flujo de aceptación del abogado
    rechaza caer silenciosamente a Mock cuando se exige un provider real.
    """

    name = "mock"
    default_model = "mock-1.0"
    supports_embeddings = False
    is_mock = True
    is_external = False

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


# =========================================================================
# V7.0 — NVIDIA NIM provider (REAL, not scaffold).
#
# Adapted from AGENTE-GENERAL's albra_seed.providers.nvidia_provider
# (HEAD 69c79da — proven against the NVIDIA NIM endpoint, with live
# smoke test at tests/llm_real/test_nvidia_glm_flash.py).
#
# The AGENTE-GENERAL NVIDIAProvider is async and uses Message objects.
# This DESPACHO-JURIDICO version is sync and uses the existing
# LLMProvider interface (generate/chat with list[dict] messages),
# preserving all 1413 existing tests.
#
# What we take from AGENTE-GENERAL (the "harness"):
#   - The proven OpenAI-compatible endpoint URL.
#   - The error classification (auth never retries; 5xx/timeout/429 retry).
#   - The discipline: never log the API key; never leak the key in errors.
#   - The `is_mock=False, is_external=True` flag pattern.
# =========================================================================


DEFAULT_NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"


def _classify_nvidia_error(exc: Exception) -> str:
    """Classify a NVIDIA NIM exception for retry / fail-closed logic.

    Returns one of:
      - 'auth'        → 401/403 — never retry, never fabricate success.
      - 'validation'  → 400 — never retry.
      - 'not_found'   → 404 (model not found) — never retry.
      - 'transient'   → 5xx, timeout, connection, 429 — retry with backoff.
      - 'unknown'     → anything else — never retry (defensive).
    """
    # Try openai-specific exception types.
    try:
        import openai
        if isinstance(exc, (openai.AuthenticationError, openai.PermissionDeniedError)):
            return "auth"
        if isinstance(exc, openai.BadRequestError):
            return "validation"
        if isinstance(exc, openai.NotFoundError):
            return "not_found"
        if isinstance(exc, (openai.APITimeoutError, openai.APIConnectionError)):
            return "transient"
        if isinstance(exc, openai.RateLimitError):
            return "transient"
        if isinstance(exc, openai.InternalServerError):
            return "transient"
        if isinstance(exc, openai.APIStatusError):
            status = getattr(exc, "status_code", None) or getattr(
                getattr(exc, "response", None), "status_code", None
            )
            if status is not None and 500 <= int(status) < 600:
                return "transient"
            if status in (401, 403):
                return "auth"
            if status == 400:
                return "validation"
            if status == 404:
                return "not_found"
            if status == 429:
                return "transient"
            return "unknown"
    except Exception:  # noqa: BLE001 — openai SDK not installed
        pass

    # Generic fallbacks for when openai SDK is not installed.
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return "transient"
    name = type(exc).__name__.lower()
    if "timeout" in name or "connection" in name:
        return "transient"
    return "unknown"


def _safe_nvidia_error_message(exc: Exception) -> str:
    """Strip any accidental key leakage from an error message.

    The openai SDK sometimes includes the URL or full request headers in
    error messages. We strip anything that looks like a Bearer token or
    nvapi-... key.
    """
    import re
    msg = f"{type(exc).__name__}: {exc}"
    msg = re.sub(r"Bearer\s+[A-Za-z0-9_\-.]{8,}", "Bearer [REDACTED]", msg)
    msg = re.sub(r"nvapi-[A-Za-z0-9_\-.]{8,}", "nvapi-[REDACTED]", msg)
    return msg


class NVIDIAProvider(LLMProvider):
    """LLM provider backed by NVIDIA NIM (OpenAI-compatible endpoint).

    Uses the ``openai`` Python SDK pointed at NVIDIA's integrate API at
    ``https://integrate.api.nvidia.com/v1``. The SDK is imported lazily
    so that tests without the ``openai`` package installed can still
    import the module — the import error only fires when the provider is
    instantiated.

    V7.0 security (mirrors AGENTE-GENERAL's discipline):
      - The API key is NEVER logged, NEVER in error messages, and NEVER
        sent to any endpoint other than ``base_url``.
      - The provider FAILS CLOSED on:
          * Missing NVIDIA_API_KEY → NotImplementedError (caller must
            handle; the RealProviderGuard turns this into BLOCKED).
          * Auth errors (401/403) → LLMResponse with empty text and
            ``metadata.failed=True``. Never retried, never fakes success.
          * Validation errors (400) → same; never retried.
          * Exhausted retries on transient errors → same.
      - Transient errors (5xx, timeout, 429) retried with exponential
        backoff up to ``max_retries`` (default 2).
      - ``is_mock=False, is_external=True`` → the lawyer acceptance flow
        trusts this provider as real.
    """

    name = "nvidia"
    default_model = "z-ai/glm-5.3-flash"
    supports_embeddings = False
    is_mock = False
    is_external = True

    def __init__(
        self,
        api_key: str | None = None,
        default_model: str | None = None,
        *,
        base_url: str | None = None,
        timeout: float = 60.0,
        max_retries: int = 2,
        temperature: float = 0.5,
        top_p: float = 1.0,
        max_tokens: int = 1024,
    ) -> None:
        # Lazily import the openai SDK. If it's not installed, raise
        # NotImplementedError with a clear install hint.
        try:
            import openai  # noqa: F401
        except ImportError as exc:
            raise NotImplementedError(
                "nvidia provider requires the 'openai' package; "
                "install with `pip install openai`"
            ) from exc

        resolved_key = api_key or os.environ.get("NVIDIA_API_KEY")
        if not resolved_key:
            raise NotImplementedError(
                "nvidia provider requires NVIDIA_API_KEY "
                "(pass api_key= or set the environment variable). "
                "Without it, the lawyer acceptance flow will BLOCK the case."
            )

        super().__init__(resolved_key, default_model)
        self.base_url = base_url or DEFAULT_NVIDIA_BASE_URL
        self.timeout = float(timeout)
        self.max_retries = int(max_retries)
        self.temperature = float(temperature)
        self.top_p = float(top_p)
        self.max_tokens = int(max_tokens)
        self._client = None  # built lazily on first call

    def _ensure_client(self) -> Any:
        """Build the OpenAI client lazily. Never logs the key."""
        if self._client is None:
            import openai
            self._client = openai.OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout,
                max_retries=0,  # we handle retries ourselves
            )
        return self._client

    def _error_response(self, exc: Exception, model: str, *, attempt: int) -> LLMResponse:
        """Build a fail-closed error response. NEVER leaks the API key."""
        category = _classify_nvidia_error(exc)
        return LLMResponse(
            text="",
            provider=self.name,
            model=model,
            tokens_in=0,
            tokens_out=0,
            usd_cost=0.0,
            latency_ms=0.0,
            metadata={
                "failed": True,
                "error_type": type(exc).__name__,
                "error_category": category,
                "safe_message": _safe_nvidia_error_message(exc),
                "attempt": attempt,
                # We NEVER include the raw exception's __repr__ here
                # because some openai exceptions embed the URL/key.
            },
        )

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Send a chat completion request to NVIDIA NIM (sync).

        Retries transient errors (5xx, timeout, 429) with exponential
        backoff. Auth (401/403), validation (400), and not_found (404)
        errors are NOT retried — the response is returned with
        ``metadata.failed=True`` and empty text.

        Returns: an LLMResponse. On success, ``text`` contains the
        completion. On failure, ``text=""`` and ``metadata.failed=True``
        plus ``metadata.error_category``.
        """
        import time as _time

        client = self._ensure_client()
        resolved_model = model or self.default_model
        t0 = _time.monotonic()

        kwargs_payload: dict[str, Any] = {
            "model": resolved_model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
            "top_p": self.top_p,
            "stream": False,
        }
        if "tools" in kwargs:
            kwargs_payload["tools"] = kwargs["tools"]

        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = client.chat.completions.create(**kwargs_payload)
                choice = response.choices[0]
                msg = choice.message
                # V7.0: GLM-5.3-flash and similar reasoning models put
                # their thinking in ``reasoning_content`` and the final
                # answer in ``content``. When content is None but
                # reasoning_content has text, the model ran out of tokens
                # before producing the final answer — fall back to the
                # reasoning content (clearly labelled) so the caller can
                # still see what the model produced.
                content = msg.content or ""
                reasoning = getattr(msg, "reasoning_content", None) or ""
                if not content and reasoning:
                    # The model exhausted tokens during reasoning. Use
                    # the reasoning content as the response, but flag it
                    # so the lawyer exam flow can require more tokens.
                    content = (
                        "[NOTA: el modelo agotó max_tokens durante el "
                        "razonamiento. Aumentando max_tokens puede "
                        "producir una respuesta final más estructurada.]\n\n"
                        + reasoning
                    )
                latency_ms = (_time.monotonic() - t0) * 1000.0
                raw_usage = getattr(response, "usage", None)
                usage_dict = raw_usage.model_dump() if raw_usage else None
                # Compute text tokens (excluding reasoning tokens) for
                # audit visibility.
                completion_tokens_details = (
                    getattr(raw_usage, "completion_tokens_details", None)
                    if raw_usage else None
                )
                text_tokens = (
                    getattr(completion_tokens_details, "text_tokens", None)
                    if completion_tokens_details else None
                )
                reasoning_tokens = (
                    getattr(completion_tokens_details, "reasoning_tokens", None)
                    if completion_tokens_details else None
                )
                return LLMResponse(
                    text=content,
                    provider=self.name,
                    model=resolved_model,
                    tokens_in=getattr(raw_usage, "prompt_tokens", 0) if raw_usage else 0,
                    tokens_out=getattr(raw_usage, "completion_tokens", 0) if raw_usage else 0,
                    usd_cost=0.0,  # NVIDIA NIM cost tracking is external (Render billing)
                    latency_ms=round(latency_ms, 2),
                    metadata={
                        "provider": self.name,
                        "model": resolved_model,
                        "attempt": attempt + 1,
                        "is_mock": False,
                        "is_external": True,
                        "usage": usage_dict,
                        "finish_reason": choice.finish_reason,
                        "reasoning_tokens": reasoning_tokens,
                        "text_tokens": text_tokens,
                    },
                )
            except Exception as exc:
                last_exc = exc
                category = _classify_nvidia_error(exc)
                if category in ("auth", "validation", "not_found", "unknown"):
                    # Non-transient — fail immediately, never retry.
                    return self._error_response(exc, resolved_model, attempt=attempt + 1)
                # Transient — retry with backoff (unless last attempt).
                if attempt < self.max_retries:
                    backoff = 0.5 * (2 ** attempt)
                    _time.sleep(backoff)
                    continue
                # Exhausted retries — return error response.
                return self._error_response(exc, resolved_model, attempt=attempt + 1)

        # Defensive: should not reach here.
        if last_exc is not None:
            return self._error_response(last_exc, resolved_model, attempt=self.max_retries + 1)
        return self._error_response(RuntimeError("unknown nvidia error"), resolved_model, attempt=0)

    def generate(
        self,
        prompt: str,
        *,
        model: str | None = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> LLMResponse:
        """Single-prompt generation → wraps chat() with one user message."""
        return self.chat(
            [{"role": "user", "content": prompt}],
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs,
        )

    def health_check(self) -> dict[str, Any]:
        """Probe health by making a minimal chat completion request.

        We send a 1-token completion and check for a 200 response. Any
        error → available=False. The API key is NEVER in the response.
        """
        try:
            resp = self.chat(
                [{"role": "user", "content": "ping"}],
                max_tokens=1,
                temperature=0,
            )
            available = not resp.metadata.get("failed", False)
            return {
                "provider": self.name,
                "available": available,
                "model": self.default_model,
                "base_url": self.base_url,
                "api_key_required": True,
                "api_key_set": bool(self.api_key),
                "is_mock": False,
                "is_external": True,
                "last_error_category": resp.metadata.get("error_category") if not available else None,
            }
        except NotImplementedError as e:
            return {
                "provider": self.name,
                "available": False,
                "model": self.default_model,
                "base_url": self.base_url,
                "api_key_required": True,
                "api_key_set": False,
                "is_mock": False,
                "is_external": True,
                "blocker": str(e),
            }
