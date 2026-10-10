"""
Provider Router - ruteo por sensibilidad.

Reglas:
- Datos sensibles (expediente, cliente, секретreto profesional) → modelo local
- Chat general → cloud
- Análisis largo → modelo con contexto grande
- Cost-aware → usar modelo más barato para tareas simples

Esto protege el secreto profesional.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from albra.config.settings import Settings
from albra.observability.logger import get_logger
from albra.providers.base import Provider


@dataclass
class RoutingDecision:
    provider: str
    reason: str
    sensitive: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class ProviderRouter:
    """Router de providers por sensibilidad."""

    SENSITIVE_KEYWORDS: tuple[str, ...] = (
        "expediente", "cliente", "dni", "cédula", "cedula", "ruc",
        "tarjeta", "cuenta", "secreto profesional", "confidencial",
        "datos personales", "información personal", "informacion personal",
        "historia clínica", "historia clinica",
    )

    LONG_CONTEXT_KEYWORDS: tuple[str, ...] = (
        "analizar", "resumir", "comparar", "documento largo",
        "contrato", "sentencia completa",
    )

    def __init__(self, settings: Settings, *, providers: dict[str, Provider]) -> None:
        self.settings = settings
        self.providers = providers
        self.log = get_logger("albra.provider_router")
        # Mapeo de tipos a providers preferidos
        self.routing_table: dict[str, str] = {
            "sensitive": "ollama_local",  # no existe por defecto - se configura
            "long_context": "anthropic",
            "chat": "openai",
            "default": "mock",
        }

    def route(self, prompt: str, *, metadata: dict[str, Any] | None = None) -> RoutingDecision:
        """Decide qué provider usar para este prompt.

        V1.6: usa Classification pasada en metadata['classification']
        si está disponible. Fallback a keywords propios.
        """
        prompt_l = prompt.lower()
        sensitive = any(k in prompt_l for k in self.SENSITIVE_KEYWORDS)
        long_ctx = any(k in prompt_l for k in self.LONG_CONTEXT_KEYWORDS) or len(prompt) > 4000

        # V1.6: usar classification si está disponible (más precisa)
        if metadata and metadata.get("classification"):
            cls_name = metadata["classification"]
            # Cualquier clasificación >= DATO_PERSONAL → sensitive
            sensitive_levels = {
                "DATO_PERSONAL", "DATO_SENSIBLE", "SECRETO_PROFESIONAL",
                "EXPEDIENTE_JURIDICO", "CREDENCIAL", "SECRETO_TECNICO",
            }
            if cls_name in sensitive_levels:
                sensitive = True

        if sensitive:
            provider_name = self.routing_table["sensitive"]
            return RoutingDecision(
                provider=provider_name,
                reason="Sensitive data detected - route to local model",
                sensitive=True,
            )
        if long_ctx:
            provider_name = self.routing_table["long_context"]
            return RoutingDecision(
                provider=provider_name,
                reason="Long context detected",
                sensitive=False,
            )
        provider_name = self.routing_table["chat"]
        return RoutingDecision(
            provider=provider_name,
            reason="Default chat",
            sensitive=False,
        )

    def get_provider(self, decision: RoutingDecision) -> Provider:
        p = self.providers.get(decision.provider)
        if not p:
            # Fallback a mock
            self.log.warning(
                "provider_router.fallback",
                requested=decision.provider,
                fallback="mock",
            )
            return self.providers["mock"]
        return p

    def set_routing(self, kind: str, provider: str) -> None:
        if kind not in self.routing_table:
            raise ValueError(f"Kind inválido: {kind}")
        self.routing_table[kind] = provider
        self.log.info("provider_router.updated", kind=kind, provider=provider)
