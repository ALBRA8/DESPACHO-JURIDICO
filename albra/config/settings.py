"""
Configuración centralizada del agente ALBRA.

P0.1 (CIERRE QUIRÚRGICO): los secretos operativos son OBLIGATORIOS.
Si ALBRA_JWT_SECRET o ALBRA_ADMIN_PASSWORD faltan o tienen defaults
conocidos → FAIL CLOSED al arrancar en modo operativo.

Los valores "change-me-in-production" y "change-me" NO son secretos
operativos - son placeholders de ejemplo en .env.example y docs.
Settings los rechaza explícitamente.

Modo test: tests pueden inyectar secretos efímeros vía entorno
(sin usar defaults inseguros).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

# Defaults conocidos - RECHAZADOS en modo operativo
KNOWN_INSECURE_JWT_SECRETS: frozenset[str] = frozenset({
    "change-me-in-production",
    "change-me",
    "",
    "secret",
    "test",
    "changeme",
})
KNOWN_INSECURE_ADMIN_PASSWORDS: frozenset[str] = frozenset({
    "change-me",
    "admin",
    "password",
    "",
    "changeme",
})


class InsecureConfigurationError(RuntimeError):
    """Levantado cuando se intenta arrancar con secretos inseguros."""


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


def _require_secret(env_key: str, *, known_insecure: frozenset[str]) -> str:
    """Lee un secreto del entorno. FAIL CLOSED si falta o es default conocido.

    NO usa valor default. Debe venir del entorno.
    """
    val = os.environ.get(env_key)
    if not val:
        raise InsecureConfigurationError(
            f"{env_key} is required. Set it via environment variable. "
            f"NO default value is provided for security."
        )
    if val in known_insecure:
        raise InsecureConfigurationError(
            f"{env_key}='{val[:20]}...' is a known insecure default. "
            f"Refusing to start. Generate a strong secret (e.g. "
            f"python -c \"import secrets; print(secrets.token_urlsafe(32))\")."
        )
    # Validación mínima de fortaleza (≥16 chars para secrets)
    if len(val) < 16:
        raise InsecureConfigurationError(
            f"{env_key} is too short ({len(val)} chars). "
            f"Use at least 16 characters. Recommended: 32+."
        )
    return val


@dataclass
class Settings:
    """Configuración viva del agente.

    P0.1: jwt_secret y admin_password son OBLIGATORIOS.
    Si el environment no los provee, fallan al primer acceso.
    """

    # Identity
    agent_name: str = field(default_factory=lambda: str(_env("ALBRA_AGENT_NAME", "DESPACHO JURÍDICO DIGITAL ALBRA")))
    agent_version: str = field(default_factory=lambda: str(_env("ALBRA_AGENT_VERSION", "1.6.0")))
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

    # Security - OBLIGATORIOS, NO tienen default operativo.
    # Se cargan via _require_secret() al primer acceso.
    # Para tests: inyectar via entorno con valores efímeros pero fuertes.
    _jwt_secret: str | None = None
    _admin_password: str | None = None

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

    @property
    def jwt_secret(self) -> str:
        """FAIL CLOSED si falta o es default conocido."""
        if self._jwt_secret is None:
            self._jwt_secret = _require_secret(
                "ALBRA_JWT_SECRET",
                known_insecure=KNOWN_INSECURE_JWT_SECRETS,
            )
        return self._jwt_secret

    @jwt_secret.setter
    def jwt_secret(self, value: str) -> None:
        """Para tests - permite inyectar secreto efímero fuerte."""
        if value in KNOWN_INSECURE_JWT_SECRETS:
            raise InsecureConfigurationError(
                f"Refusing to set insecure jwt_secret: '{value[:20]}...'"
            )
        if len(value) < 16:
            raise InsecureConfigurationError(
                f"jwt_secret too short: {len(value)} chars, need ≥16"
            )
        self._jwt_secret = value

    @property
    def admin_password(self) -> str:
        """FAIL CLOSED si falta o es default conocido."""
        if self._admin_password is None:
            self._admin_password = _require_secret(
                "ALBRA_ADMIN_PASSWORD",
                known_insecure=KNOWN_INSECURE_ADMIN_PASSWORDS,
            )
        return self._admin_password

    @admin_password.setter
    def admin_password(self, value: str) -> None:
        """Para tests - permite inyectar password efímero fuerte."""
        if value in KNOWN_INSECURE_ADMIN_PASSWORDS:
            raise InsecureConfigurationError(
                "Refusing to set insecure admin_password"
            )
        if len(value) < 8:
            raise InsecureConfigurationError(
                f"admin_password too short: {len(value)} chars, need ≥8"
            )
        self._admin_password = value

    def as_dict(self) -> dict[str, Any]:
        # NO incluir secretos en as_dict
        return {
            "agent_name": self.agent_name,
            "agent_version": self.agent_version,
            "environment": self.environment,
            "runtime_loop_max_iter": self.runtime_loop_max_iter,
            "runtime_timeout_seconds": self.runtime_timeout_seconds,
            "memory_backend": self.memory_backend,
            "memory_path": self.memory_path,
            "default_provider": self.default_provider,
            "whatsapp_enabled": self.whatsapp_enabled,
            "telegram_enabled": self.telegram_enabled,
            "log_level": self.log_level,
            "knowledge_jurisdiction": self.knowledge_jurisdiction,
        }

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
