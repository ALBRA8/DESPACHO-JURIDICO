"""
Configuración centralizada del agente ALBRA.

Principios:
- NUNCA hardcodear credenciales.
- Toda config que pueda variar debe poder sobreescribirse por env.
- Separar: config, secretos, providers, canales, tools, memoria, modelos, políticas.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


def _env(key: str, default: str | int | bool) -> str | int | bool:
    val = os.environ.get(key)
    if val is None:
        return default
    if isinstance(default, bool):
        return str(val).lower() in ("1", "true", "yes", "on")
    if isinstance(default, int):
        try:
            return int(val)
        except ValueError:
            return default
    return val


@dataclass
class Settings:
    """Configuración viva del agente. Carga desde .env o entorno."""

    # Identity
    agent_name: str = field(default_factory=lambda: str(_env("ALBRA_AGENT_NAME", "DESPACHO JURÍDICO DIGITAL ALBRA")))
    agent_version: str = field(default_factory=lambda: str(_env("ALBRA_AGENT_VERSION", "1.0.0")))
    environment: str = field(default_factory=lambda: str(_env("ALBRA_ENVIRONMENT", "development")))

    # Runtime
    runtime_loop_max_iter: int = field(default_factory=lambda: int(_env("ALBRA_RUNTIME_LOOP_MAX_ITER", 20)))
    runtime_timeout_seconds: int = field(default_factory=lambda: int(_env("ALBRA_RUNTIME_TIMEOUT_SECONDS", 120)))

    # Memory
    memory_backend: str = field(default_factory=lambda: str(_env("ALBRA_MEMORY_BACKEND", "inmemory")))
    memory_path: str = field(default_factory=lambda: str(_env("ALBRA_MEMORY_PATH", "./data/memory.db")))
    memory_embedding_model: str = field(default_factory=lambda: str(_env("ALBRA_MEMORY_EMBEDDING_MODEL", "hash")))
    memory_vector_dim: int = field(default_factory=lambda: int(_env("ALBRA_MEMORY_VECTOR_DIM", 256)))

    # Providers
    default_provider: str = field(default_factory=lambda: str(_env("ALBRA_DEFAULT_PROVIDER", "mock")))
    openai_api_key: str = field(default_factory=lambda: str(_env("ALBRA_OPENAI_API_KEY", "")))
    anthropic_api_key: str = field(default_factory=lambda: str(_env("ALBRA_ANTHROPIC_API_KEY", "")))

    # Comms
    whatsapp_enabled: bool = field(default_factory=lambda: bool(_env("ALBRA_WHATSAPP_ENABLED", False)))
    whatsapp_token: str = field(default_factory=lambda: str(_env("ALBRA_WHATSAPP_TOKEN", "")))
    whatsapp_phone_id: str = field(default_factory=lambda: str(_env("ALBRA_WHATSAPP_PHONE_ID", "")))
    telegram_enabled: bool = field(default_factory=lambda: bool(_env("ALBRA_TELEGRAM_ENABLED", False)))
    telegram_bot_token: str = field(default_factory=lambda: str(_env("ALBRA_TELEGRAM_BOT_TOKEN", "")))

    # Security
    jwt_secret: str = field(default_factory=lambda: str(_env("ALBRA_JWT_SECRET", "change-me-in-production")))
    admin_password: str = field(default_factory=lambda: str(_env("ALBRA_ADMIN_PASSWORD", "change-me")))

    # Observability
    log_level: str = field(default_factory=lambda: str(_env("ALBRA_LOG_LEVEL", "INFO")))
    log_format: str = field(default_factory=lambda: str(_env("ALBRA_LOG_FORMAT", "console")))
    audit_path: str = field(default_factory=lambda: str(_env("ALBRA_AUDIT_PATH", "./data/audit.log")))

    # Knowledge
    knowledge_jurisdiction: str = field(default_factory=lambda: str(_env("ALBRA_KNOWLEDGE_JURISDICTION", "CO")))
    knowledge_path: str = field(default_factory=lambda: str(_env("ALBRA_KNOWLEDGE_PATH", "./data/knowledge")))

    # Feature flags
    hitl_required_for: tuple[str, ...] = (
        "send_external_message",
        "publish_document",
        "modify_permissions",
        "financial_action",
        "legal_filing",
    )

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

    def is_production(self) -> bool:
        return self.environment == "production"

    def is_development(self) -> bool:
        return self.environment == "development"


# Singleton perezoso
_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    """Para testing - resetea el singleton."""
    global _settings
    _settings = None
