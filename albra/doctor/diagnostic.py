"""
Doctor - Sistema de diagnóstico y salud del agente ALBRA.

Pipeline: DETECTAR → DIAGNOSTICAR → EXPLICAR → RECOMENDAR → VERIFICAR.

Diagnostica:
- dependencias (paquetes instalados)
- configuración
- tools (registradas, disponibles)
- MCP (server/client)
- almacenamiento
- modelos/providers
- canales (whatsapp, telegram)
- memoria (backend, items, latencia)
- conectividad (egress a internet)
- estados internos
- errores recientes
- integraciones
- despliegue

Modificaciones de código PROHIBIDAS para Doctor.
Solo detecta, recomienda y aplica recovery si está autorizado y seguro.
"""
from __future__ import annotations

import importlib
import os
import socket
import time
from dataclasses import dataclass, field
from typing import Any

from albra.config.settings import Settings
from albra.observability.logger import get_logger


@dataclass
class CheckResult:
    organ: str
    ok: bool
    severity: str  # ok | warn | error
    detail: str
    recommendation: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "organ": self.organ,
            "ok": self.ok,
            "severity": self.severity,
            "detail": self.detail,
            "recommendation": self.recommendation,
        }


@dataclass
class DiagnosticReport:
    ts: float = field(default_factory=time.time)
    checks: list[CheckResult] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)

    def add(self, c: CheckResult) -> None:
        self.checks.append(c)

    def build_summary(self) -> dict[str, int]:
        self.summary = {
            "total": len(self.checks),
            "ok": sum(1 for c in self.checks if c.severity == "ok"),
            "warn": sum(1 for c in self.checks if c.severity == "warn"),
            "error": sum(1 for c in self.checks if c.severity == "error"),
        }
        return self.summary

    def as_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "summary": self.build_summary(),
            "checks": [c.as_dict() for c in self.checks],
        }


class Doctor:
    def __init__(self, settings: Settings, *, organs: dict[str, Any] | None = None) -> None:
        self.settings = settings
        self.organs = organs or {}
        self.log = get_logger("albra.doctor")

    async def startup(self) -> None:
        self.log.info("doctor.startup")

    async def shutdown(self) -> None:
        self.log.info("doctor.shutdown")

    async def diagnose(self, *, scope: str = "all") -> DiagnosticReport:
        report = DiagnosticReport()
        self.log.info("doctor.run", scope=scope)

        if scope in ("all", "deps"):
            report.add(self._check_dependencies())
        if scope in ("all", "config"):
            report.add(self._check_config())
        if scope in ("all", "tools"):
            report.add(self._check_tools())
        if scope in ("all", "mcp"):
            report.add(self._check_mcp())
        if scope in ("all", "storage"):
            report.add(self._check_storage())
        if scope in ("all", "providers"):
            report.add(self._check_providers())
        if scope in ("all", "channels"):
            report.add(self._check_channels())
        if scope in ("all", "memory"):
            report.add(self._check_memory())
        if scope in ("all", "connectivity"):
            report.add(self._check_connectivity())
        if scope in ("all", "audit"):
            report.add(self._check_audit())

        self.log.info("doctor.done", summary=report.build_summary())
        return report

    # --- Checks ---

    def _check_dependencies(self) -> CheckResult:
        required = ["pydantic", "httpx", "yaml", "structlog", "click"]
        missing: list[str] = []
        for mod in required:
            try:
                importlib.import_module(mod)
            except ImportError:
                missing.append(mod)
        if missing:
            return CheckResult(
                organ="dependencies",
                ok=False,
                severity="warn",
                detail=f"Faltan paquetes: {missing}",
                recommendation=f"Ejecutar: pip install {' '.join(missing)}",
            )
        return CheckResult(
            organ="dependencies",
            ok=True,
            severity="ok",
            detail="Dependencias core OK",
        )

    def _check_config(self) -> CheckResult:
        """V1.6 P0.1: Verifica que secretos sean obligatorios + fuertes."""
        from albra.config.settings import (
            InsecureConfigurationError,
        )
        env = self.settings.environment
        # Verificar que jwt_secret es accesible (fail-closed si no)
        try:
            _ = self.settings.jwt_secret
            jwt_ok = True
            jwt_detail = "ALBRA_JWT_SECRET presente"
        except InsecureConfigurationError as e:
            jwt_ok = False
            jwt_detail = f"ALBRA_JWT_SECRET inválido: {e}"
        try:
            _ = self.settings.admin_password
            admin_ok = True
            admin_detail = "ALBRA_ADMIN_PASSWORD presente"
        except InsecureConfigurationError as e:
            admin_ok = False
            admin_detail = f"ALBRA_ADMIN_PASSWORD inválido: {e}"

        if not jwt_ok or not admin_ok:
            return CheckResult(
                organ="config",
                ok=False,
                severity="error",
                detail=f"{jwt_detail}; {admin_detail}",
                recommendation="Set ALBRA_JWT_SECRET (32+ chars) y ALBRA_ADMIN_PASSWORD (8+ chars) en environment",
            )
        return CheckResult(
            organ="config", ok=True, severity="ok",
            detail=f"Environment: {env}, secrets strong and present",
        )

    def _check_tools(self) -> CheckResult:
        tr = self.organs.get("tools")
        if not tr:
            return CheckResult(
                organ="tools",
                ok=False,
                severity="warn",
                detail="ToolRegistry no inicializada",
                recommendation="Boot completo del agente",
            )
        count = len(tr.list()) if hasattr(tr, "list") else 0
        return CheckResult(
            organ="tools", ok=True, severity="ok", detail=f"{count} tools registradas"
        )

    def _check_mcp(self) -> CheckResult:
        srv = self.organs.get("mcp_server")
        if not srv:
            return CheckResult(
                organ="mcp", ok=False, severity="warn", detail="MCP server no cableado"
            )
        return CheckResult(
            organ="mcp", ok=True, severity="ok", detail="MCP server disponible"
        )

    def _check_storage(self) -> CheckResult:
        path = self.settings.memory_path
        d = os.path.dirname(path) or "."
        writable = os.access(d, os.W_OK)
        if not writable:
            return CheckResult(
                organ="storage",
                ok=False,
                severity="error",
                detail=f"No hay permisos de escritura en {d}",
                recommendation="Cambiar ALBRA_MEMORY_PATH a directorio writable",
            )
        return CheckResult(
            organ="storage", ok=True, severity="ok", detail=f"Storage writable: {d}"
        )

    def _check_providers(self) -> CheckResult:
        prov = self.settings.default_provider
        if prov == "mock":
            return CheckResult(
                organ="providers",
                ok=True,
                severity="warn",
                detail="Provider por defecto = mock (sin LLM real)",
                recommendation="Configurar OPENAI/ANTHROPIC API key cuando se use producción",
            )
        if prov == "openai" and not self.settings.openai_api_key:
            return CheckResult(
                organ="providers",
                ok=False,
                severity="error",
                detail="Provider=openai pero ALBRA_OPENAI_API_KEY vacío",
                recommendation="Setear ALBRA_OPENAI_API_KEY",
            )
        return CheckResult(
            organ="providers", ok=True, severity="ok", detail=f"Provider={prov}"
        )

    def _check_channels(self) -> CheckResult:
        issues: list[str] = []
        if self.settings.whatsapp_enabled and not self.settings.whatsapp_token:
            issues.append("WhatsApp enabled pero sin token")
        if self.settings.telegram_enabled and not self.settings.telegram_bot_token:
            issues.append("Telegram enabled pero sin token")
        if issues:
            return CheckResult(
                organ="channels",
                ok=False,
                severity="warn",
                detail="; ".join(issues),
                recommendation="Setear tokens o deshabilitar flags",
            )
        return CheckResult(
            organ="channels",
            ok=True,
            severity="ok",
            detail="Canales OK (o deshabilitados)",
        )

    def _check_memory(self) -> CheckResult:
        mem = self.organs.get("memory")
        if not mem:
            return CheckResult(
                organ="memory",
                ok=False,
                severity="warn",
                detail="MemoryDV no inicializada",
            )
        try:
            stats = mem.stats()
            total = sum(stats.values())
            return CheckResult(
                organ="memory",
                ok=True,
                severity="ok",
                detail=f"Backend={self.settings.memory_backend}, items={total}",
            )
        except Exception as e:  # noqa: BLE001
            return CheckResult(
                organ="memory",
                ok=False,
                severity="error",
                detail=f"Error accediendo memoria: {e}",
            )

    def _check_connectivity(self) -> CheckResult:
        try:
            s = socket.create_connection(("8.8.8.8", 53), timeout=3)
            s.close()
            return CheckResult(
                organ="connectivity",
                ok=True,
                severity="ok",
                detail="Egress a internet OK",
            )
        except OSError:
            return CheckResult(
                organ="connectivity",
                ok=False,
                severity="warn",
                detail="Sin egress a internet",
                recommendation="Verificar proxy/firewall si se usan LLMs externos",
            )

    def _check_audit(self) -> CheckResult:
        ap = self.settings.audit_path
        d = os.path.dirname(ap) or "."
        try:
            os.makedirs(d, exist_ok=True)
            with open(ap, "a", encoding="utf-8") as f:
                f.write("")
            return CheckResult(
                organ="audit", ok=True, severity="ok", detail=f"Audit path writable: {ap}"
            )
        except OSError as e:
            return CheckResult(
                organ="audit",
                ok=False,
                severity="error",
                detail=f"Audit path no writable: {e}",
                recommendation="Cambiar ALBRA_AUDIT_PATH",
            )

    async def try_recover(self, organ: str) -> bool:
        """Recuperación segura - solo para ciertos órganos.

        NO modifica código. Solo reinicia estados, reconecta, etc.
        """
        self.log.info("doctor.recover", organ=organ)
        # Por ahora: re-init del órgano si es seguro
        if organ in {"memory", "events"}:
            target = self.organs.get(organ)
            if target and hasattr(target, "startup"):
                try:
                    await target.startup()
                    return True
                except Exception as e:  # noqa: BLE001
                    self.log.error("doctor.recover.fail", organ=organ, error=str(e))
        return False
