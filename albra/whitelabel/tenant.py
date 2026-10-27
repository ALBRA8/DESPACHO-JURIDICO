"""
TENANT — dataclass + TenantManager para la white-label platform V2.5-B.

Inspiración clean-room:
- case.dev (white-label platform con monthly minimum or annual commitment,
  permite a otros firms montar su propio agentic IDE bajo su marca).
- LawVu (Microsoft sensitivity labels integration for tenant isolation —
  cada tenant con su propia data classification + retention).
- Gotham (data residency garantizada en el país del cliente — para ALBRA
  esto significa data/tenants/<tenant_id>/ aislado del resto).

V2.5-B: TenantManager con SQLite WAL multi-tenant safe. Cada tenant
tiene su propio matter_data_dir y audit_log_path bajo data_root.

V2.5+: Stripe/USDC billing integration (webhook → update_license),
SaaS deployment con subdomain routing (slug.tenant.albra.co), y
data residency configurable por país (Colombia /LATAM-default).

Cada Tenant:
- id: UUID (str canonico con dashes, generado por uuid.uuid4())
- name: display name del despacho
- slug: kebab-case para URLs (regex ^[a-z0-9]+(-[a-z0-9]+)*$)
- branding: dict con 5 claves (primary_color, secondary_color, logo_url,
            font_family, agent_name_override)
- feature_flags: dict con 9 claves (6 bool + 3 int max_*)
- license: dict con 4 claves (type, expires_at, monthly_price_usd, contact_email)
- audit_config: dict con 2 claves (audit_log_path, retention_years)
- created_at: ISO 8601 UTC timestamp

Default feature_flags por license_type:
- trial: 30 días, max_matters=5, max_agents=1, marketplace OFF
- pro: 365 días, max_matters=100, max_agents=10, marketplace ON
- enterprise: 365 días, max_*=-1 (unlimited), marketplace ON
"""
from __future__ import annotations

import json
import re
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from albra.observability.logger import get_logger

__all__ = [
    "Tenant",
    "TenantManager",
    "TenantValidationError",
    "get_manager",
    "reset_manager",
]

_VALID_LICENSE_TYPES: frozenset[str] = frozenset({"trial", "pro", "enterprise"})

# V2.5-B defaults per license_type (case.dev-style tiering).
_DEFAULT_FEATURE_FLAGS_BY_LICENSE: dict[str, dict[str, Any]] = {
    "trial": {
        "enable_redline_docx": True,
        "enable_rag_local": True,
        "enable_citation_graph": True,
        "enable_precedent_board": True,
        "enable_tabular_review": True,
        "enable_marketplace": False,
        "max_matters": 5,
        "max_agents": 1,
        "max_audit_entries": 1000,
    },
    "pro": {
        "enable_redline_docx": True,
        "enable_rag_local": True,
        "enable_citation_graph": True,
        "enable_precedent_board": True,
        "enable_tabular_review": True,
        "enable_marketplace": True,
        "max_matters": 100,
        "max_agents": 10,
        "max_audit_entries": 100_000,
    },
    "enterprise": {
        "enable_redline_docx": True,
        "enable_rag_local": True,
        "enable_citation_graph": True,
        "enable_precedent_board": True,
        "enable_tabular_review": True,
        "enable_marketplace": True,
        "max_matters": -1,  # unlimited
        "max_agents": -1,
        "max_audit_entries": -1,
    },
}

_DEFAULT_LICENSE_TERM_DAYS: dict[str, int] = {
    "trial": 30,
    "pro": 365,
    "enterprise": 365,
}

_DEFAULT_LICENSE_PRICING: dict[str, float] = {
    "trial": 0.0,
    "pro": 199.0,
    "enterprise": 999.0,
}

_DEFAULT_BRANDING: dict[str, str] = {
    "primary_color": "#0B5394",  # ALBRA blue
    "secondary_color": "#FFD966",  # ALBRA yellow
    "logo_url": "",
    "font_family": "Inter, system-ui, sans-serif",
    "agent_name_override": "",
}

_DEFAULT_AUDIT_RETENTION_YEARS: int = 10

# kebab-case regex: lowercase alphanumeric + dashes, must start/end alphanumeric.
_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _validate_slug(slug: str) -> bool:
    """Slug debe ser kebab-case: ^[a-z0-9]+(-[a-z0-9]+)*$ y ≤ 64 chars."""
    if not slug or len(slug) > 64:
        return False
    return bool(_SLUG_RE.match(slug))


class TenantValidationError(ValueError):
    """Levantado cuando un Tenant es inválido o slug está duplicado."""


@dataclass
class Tenant:
    """Definición de un tenant del white-label platform.

    Cada tenant es un despacho colombiano que licencia ALBRA bajo su propia
    marca. Inspirado en case.dev (white-label platform), LawVu (sensitivity
    labels for tenant isolation) y Gotham (data residency garantizada).

    El tenant_id aísla físicamente los datos: matter_data_dir y audit_log_path
    son subdirectorios de data_root dedicados al tenant.
    """

    id: str
    name: str
    slug: str
    branding: dict[str, Any] = field(default_factory=dict)
    feature_flags: dict[str, Any] = field(default_factory=dict)
    license: dict[str, Any] = field(default_factory=dict)
    audit_config: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Serializa el tenant para API/JSON responses.

        Copy defensiva de dicts (no aliasing entre Tenant y dict retornado).
        """
        return {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "branding": dict(self.branding),
            "feature_flags": dict(self.feature_flags),
            "license": dict(self.license),
            "audit_config": dict(self.audit_config),
            "created_at": self.created_at,
        }

    @property
    def matter_data_dir(self) -> str:
        """Directorio aislado para matters del tenant.

        V2.5-B: data/tenants/<tenant_id>/matters/ — LawVu-style tenant
        isolation. Cada tenant tiene su propio MatterStore.db aquí
        (V2.5+ MatterStore acepta db_path por tenant).
        """
        return f"data/tenants/{self.id}/matters"

    @property
    def audit_log_path(self) -> str:
        """Path al audit log del tenant (per-tenant isolation).

        Si audit_config.audit_log_path está seteado explícitamente se usa
        ese (V2.5+: data residency configurable por país). Si no, default
        data/tenants/<tenant_id>/audit/audit.log.
        """
        custom = self.audit_config.get("audit_log_path", "")
        if custom:
            return custom
        return f"data/tenants/{self.id}/audit/audit.log"


class TenantManager:
    """Registry SQLite multi-tenant para la white-label platform V2.5-B.

    Cada tenant se persiste en SQLite WAL con aislamiento físico por
    data_root/data/tenants/<tenant_id>/. El schema usa UNIQUE en slug para
    prevenir duplicados a nivel DB (defensa en profundidad además del check
    explícito en create_tenant).

    Usage::

        mgr = TenantManager()
        tid = mgr.create_tenant("Bufete Pérez & Asociados",
                                "perez-asociados", license_type="pro")
        t = mgr.get_tenant(tid)
        mgr.update_branding(tid, {"primary_color": "#ff0000"})
        mgr.is_feature_enabled(tid, "enable_marketplace")  # → True (pro)
        mgr.is_license_valid(tid)  # → True si no expirado
        mgr.stats()  # → {total_tenants, by_license_type, ...}
    """

    def __init__(
        self,
        db_path: str = "./data/tenants.db",
        data_root: str = "./data/tenants",
    ) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.data_root = Path(data_root)
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.log = get_logger("albra.whitelabel")
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _init_db(self) -> None:
        # WAL mode: lectores no bloquean escritor (CLI + API concurrente).
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tenants (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                slug TEXT UNIQUE NOT NULL,
                branding_json TEXT NOT NULL DEFAULT '{}',
                feature_flags_json TEXT NOT NULL DEFAULT '{}',
                license_json TEXT NOT NULL DEFAULT '{}',
                audit_config_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_tenants_slug ON tenants(slug);
            """
        )
        self._conn.commit()

    # ===== CRUD =====

    def create_tenant(
        self,
        name: str,
        slug: str,
        license_type: str = "trial",
    ) -> str:
        """Crea un tenant con defaults según license_type.

        Args:
            name: Display name del despacho (p. ej. "Bufete Pérez & Asociados").
            slug: kebab-case para URLs (p. ej. "perez-asociados").
            license_type: trial | pro | enterprise.

        Returns:
            tenant_id (UUID canonical str).

        Raises:
            TenantValidationError: si name vacío, slug inválido o duplicado,
                o license_type inválido.
        """
        if not name or not name.strip():
            raise TenantValidationError("name is required")
        if not _validate_slug(slug):
            raise TenantValidationError(
                f"invalid slug: {slug!r} (kebab-case required, "
                f"pattern: ^[a-z0-9]+(-[a-z0-9]+)*$)"
            )
        if license_type not in _VALID_LICENSE_TYPES:
            raise TenantValidationError(
                f"invalid license_type: {license_type!r}. "
                f"Valid: {sorted(_VALID_LICENSE_TYPES)}"
            )

        # Slug uniqueness check explícito (la UNIQUE constraint en DB
        # también lo enforcería con IntegrityError, pero mejor mensaje).
        if self.get_tenant_by_slug(slug) is not None:
            raise TenantValidationError(f"slug already taken: {slug!r}")

        tenant_id = str(uuid.uuid4())
        now = _utcnow_iso()
        expires_at = (
            datetime.now(timezone.utc)
            + timedelta(days=_DEFAULT_LICENSE_TERM_DAYS[license_type])
        ).date().isoformat()

        branding = dict(_DEFAULT_BRANDING)
        feature_flags = dict(_DEFAULT_FEATURE_FLAGS_BY_LICENSE[license_type])
        license_dict: dict[str, Any] = {
            "type": license_type,
            "expires_at": expires_at,
            "monthly_price_usd": _DEFAULT_LICENSE_PRICING[license_type],
            "contact_email": "",
        }
        audit_config: dict[str, Any] = {
            "audit_log_path": str(self.data_root / tenant_id / "audit" / "audit.log"),
            "retention_years": _DEFAULT_AUDIT_RETENTION_YEARS,
        }

        self._conn.execute(
            """
            INSERT INTO tenants
            (id, name, slug, branding_json, feature_flags_json,
             license_json, audit_config_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tenant_id,
                name,
                slug,
                json.dumps(branding, ensure_ascii=False),
                json.dumps(feature_flags, ensure_ascii=False),
                json.dumps(license_dict, ensure_ascii=False),
                json.dumps(audit_config, ensure_ascii=False),
                now,
            ),
        )
        # Tenant isolation: crear matter_data_dir + audit dir físicamente.
        (self.data_root / tenant_id / "matters").mkdir(parents=True, exist_ok=True)
        (self.data_root / tenant_id / "audit").mkdir(parents=True, exist_ok=True)
        self._conn.commit()
        self.log.info(
            "tenant.create",
            tenant_id=tenant_id,
            name=name,
            slug=slug,
            license_type=license_type,
        )
        return tenant_id

    def get_tenant(self, tenant_id: str) -> Tenant | None:
        """Devuelve el Tenant con ese id, o None si no existe."""
        if self._conn is None:
            return None
        cur = self._conn.execute(
            "SELECT id, name, slug, branding_json, feature_flags_json, "
            "license_json, audit_config_json, created_at "
            "FROM tenants WHERE id = ?",
            (tenant_id,),
        )
        row = cur.fetchone()
        return self._row_to_tenant(row) if row else None

    def get_tenant_by_slug(self, slug: str) -> Tenant | None:
        """Devuelve el Tenant con ese slug, o None si no existe."""
        if self._conn is None:
            return None
        cur = self._conn.execute(
            "SELECT id, name, slug, branding_json, feature_flags_json, "
            "license_json, audit_config_json, created_at "
            "FROM tenants WHERE slug = ?",
            (slug,),
        )
        row = cur.fetchone()
        return self._row_to_tenant(row) if row else None

    def list_tenants(self) -> list[Tenant]:
        """Lista todos los tenants ordenados por created_at ASC."""
        if self._conn is None:
            return []
        cur = self._conn.execute(
            "SELECT id, name, slug, branding_json, feature_flags_json, "
            "license_json, audit_config_json, created_at "
            "FROM tenants ORDER BY created_at ASC"
        )
        return [self._row_to_tenant(row) for row in cur.fetchall()]

    # ===== Updates (merge semántico) =====

    def update_branding(
        self,
        tenant_id: str,
        branding: dict[str, Any],
    ) -> Tenant:
        """Merge parcial de branding keys. Devuelve el Tenant actualizado.

        Solo las claves pasadas en `branding` se sobreescriben; las demás
        se conservan (semántica PATCH, no PUT).
        """
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            raise KeyError(f"Tenant not found: {tenant_id}")
        merged = dict(tenant.branding)
        merged.update(branding)
        self._conn.execute(
            "UPDATE tenants SET branding_json = ? WHERE id = ?",
            (json.dumps(merged, ensure_ascii=False), tenant_id),
        )
        self._conn.commit()
        self.log.info(
            "tenant.update.branding",
            tenant_id=tenant_id,
            keys=list(branding.keys()),
        )
        updated = self.get_tenant(tenant_id)
        assert updated is not None  # acabamos de actualizar
        return updated

    def update_feature_flags(
        self,
        tenant_id: str,
        flags: dict[str, Any],
    ) -> Tenant:
        """Merge parcial de feature_flags. Devuelve el Tenant actualizado."""
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            raise KeyError(f"Tenant not found: {tenant_id}")
        merged = dict(tenant.feature_flags)
        merged.update(flags)
        self._conn.execute(
            "UPDATE tenants SET feature_flags_json = ? WHERE id = ?",
            (json.dumps(merged, ensure_ascii=False), tenant_id),
        )
        self._conn.commit()
        self.log.info(
            "tenant.update.feature_flags",
            tenant_id=tenant_id,
            keys=list(flags.keys()),
        )
        updated = self.get_tenant(tenant_id)
        assert updated is not None
        return updated

    def update_license(
        self,
        tenant_id: str,
        license: dict[str, Any],  # noqa: A002 — spec API uses `license`
    ) -> Tenant:
        """Merge parcial de license. Devuelve el Tenant actualizado.

        Si se actualiza `type`, debe ser uno de trial | pro | enterprise.
        V2.5+: Stripe webhook llamará esto con {expires_at, monthly_price_usd}
        tras confirmación de pago.
        """
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            raise KeyError(f"Tenant not found: {tenant_id}")
        merged = dict(tenant.license)
        merged.update(license)
        # Validate type if present
        if "type" in merged and merged["type"] not in _VALID_LICENSE_TYPES:
            raise TenantValidationError(
                f"invalid license type: {merged['type']!r}. "
                f"Valid: {sorted(_VALID_LICENSE_TYPES)}"
            )
        self._conn.execute(
            "UPDATE tenants SET license_json = ? WHERE id = ?",
            (json.dumps(merged, ensure_ascii=False), tenant_id),
        )
        self._conn.commit()
        self.log.info(
            "tenant.update.license",
            tenant_id=tenant_id,
            keys=list(license.keys()),
        )
        updated = self.get_tenant(tenant_id)
        assert updated is not None
        return updated

    # ===== Queries =====

    def is_feature_enabled(self, tenant_id: str, flag: str) -> bool:
        """Devuelve True si el flag (bool) está habilitado para el tenant.

        Fail-closed: tenant inexistente o flag ausente → False.
        Para flags `max_*` (int, no bool) también devuelve False (no es
        su rol responder esa pregunta — V2.5+ tendrá max_reached(tenant_id,
        flag) para eso).
        """
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return False
        value = tenant.feature_flags.get(flag)
        return bool(value) if isinstance(value, bool) else False

    def is_license_valid(self, tenant_id: str) -> bool:
        """Devuelve True si el license del tenant no ha expirado.

        Fail-closed: tenant inexistente, license sin expires_at, o fecha
        inválida → False. Compara expires_at (ISO date o ISO datetime)
        contra datetime.now(timezone.utc).
        """
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return False
        expires_at = tenant.license.get("expires_at")
        if not expires_at:
            return False
        try:
            # Soporta tanto "2025-12-31" como "2025-12-31T23:59:59+00:00"
            exp = datetime.fromisoformat(expires_at)
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            return exp > datetime.now(timezone.utc)
        except ValueError:
            return False

    def delete_tenant(self, tenant_id: str) -> bool:
        """Elimina un tenant del registry.

        Returns:
            True si se eliminó, False si no existía.
            V2.5+: MatterStore + audit data del tenant se eliminan aparte
            (GDPR-style hard delete asincrónico, configurable retention).
        """
        if self._conn is None:
            return False
        cur = self._conn.execute(
            "DELETE FROM tenants WHERE id = ?",
            (tenant_id,),
        )
        self._conn.commit()
        deleted = cur.rowcount > 0
        if deleted:
            self.log.info("tenant.delete", tenant_id=tenant_id)
        return deleted

    # ===== Stats =====

    def stats(self) -> dict[str, Any]:
        """Devuelve métricas del registry.

        Returns:
            {
                "total_tenants": int,
                "by_license_type": dict[str, int],
                "active_licenses": int,  # no expirados
                "db_path": str,
            }
        """
        tenants = self.list_tenants()
        by_license: dict[str, int] = {}
        for t in tenants:
            lt = str(t.license.get("type", "unknown"))
            by_license[lt] = by_license.get(lt, 0) + 1
        active = sum(1 for t in tenants if self.is_license_valid(t.id))
        return {
            "total_tenants": len(tenants),
            "by_license_type": by_license,
            "active_licenses": active,
            "db_path": str(self.db_path),
        }

    # ===== Lifecycle =====

    def close(self) -> None:
        """Cierra la conexión SQLite. Llamadas posteriores son safe no-op."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            self.log.info("tenant_manager.closed")

    # ===== Internal =====

    def _row_to_tenant(self, row: tuple[Any, ...]) -> Tenant:
        """Construye un Tenant desde una fila de SQLite."""
        return Tenant(
            id=row[0],
            name=row[1],
            slug=row[2],
            branding=json.loads(row[3]) if row[3] else {},
            feature_flags=json.loads(row[4]) if row[4] else {},
            license=json.loads(row[5]) if row[5] else {},
            audit_config=json.loads(row[6]) if row[6] else {},
            created_at=row[7],
        )


# =========================================================================
# SINGLETON (V2.5-B: lazy + resettable para tests — pattern de marketplace)
# =========================================================================

_manager: TenantManager | None = None


def get_manager() -> TenantManager:
    """Devuelve el TenantManager singleton global (lazy init).

    Para tests: ``reset_manager()`` o ``monkeypatch.setattr(module,
    "_manager", None)`` resetean el singleton.
    """
    global _manager
    if _manager is None:
        _manager = TenantManager()
    return _manager


def reset_manager() -> None:
    """Resetea el singleton global (para tests). Cierra la conn si abierta."""
    global _manager
    if _manager is not None:
        _manager.close()
    _manager = None
