"""Tests del White-label Platform V2.5-B.

Cobertura (15 tests):
- create_tenant returns UUID str
- create_tenant persists with all defaults (branding/feature_flags/license/audit_config/created_at)
- create_tenant trial defaults (max_matters=5, marketplace OFF, expires +30 days)
- create_tenant pro defaults (max_matters=100, marketplace ON, monthly_price 199)
- create_tenant enterprise defaults (max_matters=-1 unlimited)
- create_tenant creates isolated matter_data_dir + audit dir
- create_tenant invalid slug raises TenantValidationError
- create_tenant duplicate slug raises
- create_tenant invalid license_type raises
- get_tenant_by_slug + get_tenant unknown returns None
- list_tenants returns all (ordered by created_at)
- update_branding merges partial (PATCH semantics)
- update_feature_flags merges (max_matters updated, others preserved)
- update_license merges (expires_at updated, type preserved; invalid type raises)
- is_feature_enabled (True/False/unknown tenant fail-closed)
- is_license_valid (active True, expired False, unknown False)
- delete_tenant removes + returns bool
- stats returns counts (total_tenants, by_license_type, active_licenses, db_path)
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from albra.whitelabel import (
    Tenant,
    TenantManager,
    TenantValidationError,
)
from albra.whitelabel import tenant as wl_module

# ===== Fixtures =====


@pytest.fixture
def strong_secrets(monkeypatch):
    """Secretos efímeros requeridos por settings.Settings (V1.5 security)."""
    monkeypatch.setenv("ALBRA_JWT_SECRET", "test-ephemeral-jwt-secret-32-chars")
    monkeypatch.setenv("ALBRA_ADMIN_PASSWORD", "test-ephemeral-pass-1234")


@pytest.fixture
def manager(strong_secrets, tmp_path):
    """Fresh TenantManager con SQLite en tmp_path (aislado por test)."""
    db_path = tmp_path / "tenants.db"
    data_root = tmp_path / "tenants"
    mgr = TenantManager(db_path=str(db_path), data_root=str(data_root))
    yield mgr
    mgr.close()


# ===== create_tenant =====


def test_create_tenant_returns_uuid_str(manager):
    """create_tenant devuelve un UUID canonical str (con dashes)."""
    tid = manager.create_tenant("Bufete Pérez & Asociados", "perez-asociados")
    assert isinstance(tid, str)
    assert len(tid) == 36  # canonical UUID: 8-4-4-4-12 = 36 chars con dashes
    parts = tid.split("-")
    assert len(parts) == 5


def test_create_tenant_persists_with_defaults(manager):
    """get_tenant devuelve un Tenant con todos los campos defaults."""
    tid = manager.create_tenant("BufetenTest", "bufete-test")
    t = manager.get_tenant(tid)
    assert t is not None
    assert t.id == tid
    assert t.name == "BufetenTest"
    assert t.slug == "bufete-test"
    assert t.created_at != ""
    # Branding defaults
    assert "primary_color" in t.branding
    assert "font_family" in t.branding
    assert t.branding["agent_name_override"] == ""
    # Feature flags default (trial)
    assert t.feature_flags["enable_redline_docx"] is True
    assert t.feature_flags["enable_marketplace"] is False
    assert t.feature_flags["max_matters"] == 5
    # License defaults
    assert t.license["type"] == "trial"
    assert t.license["monthly_price_usd"] == 0.0
    assert t.license["expires_at"] != ""
    # Audit config defaults
    assert "audit_log_path" in t.audit_config
    assert "retention_years" in t.audit_config
    assert t.audit_config["retention_years"] == 10


def test_create_tenant_trial_defaults(manager):
    """Trial: 30 días expiry, max_matters=5, marketplace OFF."""
    tid = manager.create_tenant("Trial Law", "trial-law", license_type="trial")
    t = manager.get_tenant(tid)
    assert t is not None
    assert t.license["type"] == "trial"
    assert t.license["monthly_price_usd"] == 0.0
    assert t.feature_flags["enable_marketplace"] is False
    assert t.feature_flags["max_matters"] == 5
    assert t.feature_flags["max_agents"] == 1
    assert t.feature_flags["max_audit_entries"] == 1000
    # Expiry debe ser ~30 días en el futuro
    exp = datetime.fromisoformat(t.license["expires_at"]).replace(tzinfo=timezone.utc)
    delta = exp - datetime.now(timezone.utc)
    assert 29 <= delta.days <= 31


def test_create_tenant_pro_defaults(manager):
    """Pro: 365 días expiry, max_matters=100, marketplace ON, $199/mo."""
    tid = manager.create_tenant("Pro Law", "pro-law", license_type="pro")
    t = manager.get_tenant(tid)
    assert t is not None
    assert t.license["type"] == "pro"
    assert t.license["monthly_price_usd"] == 199.0
    assert t.feature_flags["enable_marketplace"] is True
    assert t.feature_flags["max_matters"] == 100
    assert t.feature_flags["max_agents"] == 10
    assert t.feature_flags["max_audit_entries"] == 100_000


def test_create_tenant_enterprise_defaults(manager):
    """Enterprise: unlimited (-1) max_*, marketplace ON, $999/mo."""
    tid = manager.create_tenant("Enterprise Law", "enterprise-law", license_type="enterprise")
    t = manager.get_tenant(tid)
    assert t is not None
    assert t.license["type"] == "enterprise"
    assert t.license["monthly_price_usd"] == 999.0
    assert t.feature_flags["enable_marketplace"] is True
    assert t.feature_flags["max_matters"] == -1
    assert t.feature_flags["max_agents"] == -1
    assert t.feature_flags["max_audit_entries"] == -1


def test_create_tenant_creates_isolated_matter_data_dir(manager):
    """LawVu-style isolation: data/tenants/<id>/matters/ + audit/ existen."""
    tid = manager.create_tenant("Iso Law", "iso-law")
    matters_dir = Path(manager.data_root) / tid / "matters"
    audit_dir = Path(manager.data_root) / tid / "audit"
    assert matters_dir.exists()
    assert matters_dir.is_dir()
    assert audit_dir.exists()
    assert audit_dir.is_dir()
    # Tenant.audit_log_path property reflects per-tenant path
    t = manager.get_tenant(tid)
    assert t is not None
    assert tid in t.audit_log_path
    assert "audit" in t.audit_log_path


def test_create_tenant_invalid_slug_raises(manager):
    """Slug inválido (uppercase, spaces, special chars) → TenantValidationError."""
    bad_slugs = [
        "Perez-Asociados",  # uppercase
        "perez asociados",  # space
        "perez_&_asociados",  # underscores + ampersand
        "-leading-dash",
        "trailing-dash-",
        "",
    ]
    for slug in bad_slugs:
        with pytest.raises(TenantValidationError, match="invalid slug"):
            manager.create_tenant("Bad Slug Co", slug)


def test_create_tenant_duplicate_slug_raises(manager):
    """Slug duplicado → TenantValidationError con mensaje 'already taken'."""
    manager.create_tenant("First Firm", "perez-asociados")
    with pytest.raises(TenantValidationError, match="already taken"):
        manager.create_tenant("Different Firm Same Slug", "perez-asociados")


def test_create_tenant_invalid_license_type_raises(manager):
    """license_type inválido → TenantValidationError con mensaje 'invalid'."""
    with pytest.raises(TenantValidationError, match="invalid license_type"):
        manager.create_tenant("Bad License", "bad-license", license_type="free")


# ===== get_tenant + list_tenants =====


def test_get_tenant_by_slug_and_unknown_returns_none(manager):
    """get_tenant_by_slug encuentra el tenant; get_tenant(None) returns None."""
    tid = manager.create_tenant("Slug Firm", "slug-firm")
    by_slug = manager.get_tenant_by_slug("slug-firm")
    assert by_slug is not None
    assert by_slug.id == tid
    assert manager.get_tenant("nonexistent-id-12345") is None
    assert manager.get_tenant_by_slug("nonexistent-slug") is None


def test_list_tenants_returns_all_ordered(manager):
    """list_tenants devuelve todos los tenants creados."""
    id1 = manager.create_tenant("Firm One", "firm-one")
    id2 = manager.create_tenant("Firm Two", "firm-two")
    id3 = manager.create_tenant("Firm Three", "firm-three")
    tenants = manager.list_tenants()
    assert len(tenants) == 3
    ids = [t.id for t in tenants]
    assert id1 in ids and id2 in ids and id3 in ids


# ===== Updates (PATCH semantics) =====


def test_update_branding_merges_partial(manager):
    """update_branding solo sobreescribe las claves pasadas (PATCH)."""
    tid = manager.create_tenant("Brand Firm", "brand-firm")
    original = manager.get_tenant(tid)
    assert original is not None
    original_font = original.branding["font_family"]
    original_secondary = original.branding["secondary_color"]

    updated = manager.update_branding(tid, {
        "primary_color": "#ff0000",
        "agent_name_override": "AGENTE PEREZ",
    })
    assert updated.branding["primary_color"] == "#ff0000"
    assert updated.branding["agent_name_override"] == "AGENTE PEREZ"
    # Unchanged keys preserved
    assert updated.branding["font_family"] == original_font
    assert updated.branding["secondary_color"] == original_secondary


def test_update_feature_flags_merges(manager):
    """update_feature_flags mergea flags nuevas (max_matters) + conserva bools."""
    tid = manager.create_tenant("Flags Firm", "flags-firm")
    updated = manager.update_feature_flags(tid, {
        "max_matters": 250,
        "enable_marketplace": True,
    })
    assert updated.feature_flags["max_matters"] == 250
    assert updated.feature_flags["enable_marketplace"] is True
    # Unchanged flags preserved
    assert updated.feature_flags["enable_redline_docx"] is True
    assert updated.feature_flags["max_agents"] == 1  # trial default


def test_update_license_merges_and_validates_type(manager):
    """update_license mergea + valida type si viene en el payload."""
    tid = manager.create_tenant("License Firm", "license-firm")
    original = manager.get_tenant(tid)
    assert original is not None
    original_type = original.license["type"]
    original_price = original.license["monthly_price_usd"]

    # Patch expires_at + contact_email, type preserved
    new_expiry = (datetime.now(timezone.utc) + timedelta(days=730)).date().isoformat()
    updated = manager.update_license(tid, {
        "expires_at": new_expiry,
        "contact_email": "billing@firminc.co",
    })
    assert updated.license["expires_at"] == new_expiry
    assert updated.license["contact_email"] == "billing@firminc.co"
    assert updated.license["type"] == original_type  # preserved
    assert updated.license["monthly_price_usd"] == original_price  # preserved

    # Now upgrade to pro
    upgraded = manager.update_license(tid, {"type": "pro", "monthly_price_usd": 199.0})
    assert upgraded.license["type"] == "pro"
    assert upgraded.license["monthly_price_usd"] == 199.0

    # Invalid type raises
    with pytest.raises(TenantValidationError, match="invalid license type"):
        manager.update_license(tid, {"type": "free"})


# ===== is_feature_enabled + is_license_valid =====


def test_is_feature_enabled(manager):
    """is_feature_enabled: True para bool True, False para bool False, False unknown."""
    tid = manager.create_tenant("Feature Firm", "feature-firm")  # trial
    assert manager.is_feature_enabled(tid, "enable_redline_docx") is True
    assert manager.is_feature_enabled(tid, "enable_marketplace") is False  # trial OFF
    # max_matters is int, not bool → False (not its role)
    assert manager.is_feature_enabled(tid, "max_matters") is False
    # Unknown flag → False
    assert manager.is_feature_enabled(tid, "nonexistent_flag") is False
    # Unknown tenant → False (fail-closed)
    assert manager.is_feature_enabled("nonexistent-tenant", "enable_redline_docx") is False


def test_is_license_valid_active_expired_unknown(manager):
    """is_license_valid: True activo, False expirado, False tenant inexistente."""
    tid = manager.create_tenant("License Valid", "license-valid")  # trial 30d
    assert manager.is_license_valid(tid) is True
    # Unknown tenant → False
    assert manager.is_license_valid("nonexistent-tenant") is False
    # Manually expire: set expires_at to past
    manager.update_license(tid, {
        "expires_at": (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat(),
    })
    assert manager.is_license_valid(tid) is False
    # Invalid expires_at format → False
    manager.update_license(tid, {"expires_at": "not-a-date"})
    assert manager.is_license_valid(tid) is False


# ===== delete + stats =====


def test_delete_tenant_removes_and_returns_bool(manager):
    """delete_tenant: True si existía, False si no."""
    tid = manager.create_tenant("Delete Me", "delete-me")
    assert manager.delete_tenant(tid) is True
    assert manager.get_tenant(tid) is None
    # Second delete → False (already gone)
    assert manager.delete_tenant(tid) is False
    # Delete unknown → False
    assert manager.delete_tenant("nonexistent-id-9999") is False


def test_stats_returns_counts(manager):
    """stats devuelve total_tenants, by_license_type, active_licenses, db_path."""
    manager.create_tenant("Stats Trial", "stats-trial")  # trial
    manager.create_tenant("Stats Pro", "stats-pro", license_type="pro")
    manager.create_tenant("Stats Ent", "stats-ent", license_type="enterprise")
    stats = manager.stats()
    assert stats["total_tenants"] == 3
    assert stats["by_license_type"] == {"trial": 1, "pro": 1, "enterprise": 1}
    assert stats["active_licenses"] == 3  # all freshly created
    assert "db_path" in stats
    assert "tenants.db" in stats["db_path"]


# ===== Persistence + edge cases =====


def test_persistence_across_connections(tmp_path, strong_secrets):
    """Tenant creado en una conn sobrevive a otra conn (mismo db_path)."""
    db_path = tmp_path / "tenants.db"
    data_root = tmp_path / "tenants"
    mgr1 = TenantManager(db_path=str(db_path), data_root=str(data_root))
    tid = mgr1.create_tenant("Persist Firm", "persist-firm", license_type="pro")
    mgr1.close()

    # New connection, same db_path → tenant visible
    mgr2 = TenantManager(db_path=str(db_path), data_root=str(data_root))
    t = mgr2.get_tenant(tid)
    assert t is not None
    assert t.name == "Persist Firm"
    assert t.slug == "persist-firm"
    assert t.license["type"] == "pro"
    mgr2.close()


def test_tenant_as_dict_has_all_fields(manager):
    """Tenant.as_dict() devuelve dict con las 8 claves + copy defensiva."""
    tid = manager.create_tenant("Dict Firm", "dict-firm")
    t = manager.get_tenant(tid)
    assert t is not None
    d = t.as_dict()
    expected_keys = {
        "id", "name", "slug", "branding",
        "feature_flags", "license", "audit_config", "created_at",
    }
    assert set(d.keys()) == expected_keys
    # Mutating the returned dict should not affect the Tenant
    d["branding"]["primary_color"] = "#000000"
    assert t.branding["primary_color"] != "#000000"


def test_sqlite_unique_constraint_enforced(manager):
    """Inserción directa con slug duplicado en SQLite debe violar UNIQUE."""
    manager.create_tenant("First Co", "dup-test")
    # Inspección directa: intentar INSERT con el mismo slug debe fallar
    with pytest.raises(sqlite3.IntegrityError):
        manager._conn.execute(  # noqa: SLF001 — testing internal DB invariance
            "INSERT INTO tenants (id, name, slug, branding_json, "
            "feature_flags_json, license_json, audit_config_json, created_at) "
            "VALUES (?, ?, ?, '{}', '{}', '{}', '{}', ?)",
            ("fake-uuid", "Second Co", "dup-test", "2025-01-01T00:00:00+00:00"),
        )


def test_json_persistence_roundtrip_unicode(manager):
    """Nombres con acentos/Unicode sobreviven el JSON roundtrip."""
    tid = manager.create_tenant("Bufete Pérez & Asociados", "perez-asociados")
    t = manager.get_tenant(tid)
    assert t is not None
    assert t.name == "Bufete Pérez & Asociados"
    # Verificar que el JSON en DB también conserva los acentos (no \uXXXX)
    cur = manager._conn.execute(  # noqa: SLF001
        "SELECT name FROM tenants WHERE id = ?", (tid,)
    )
    raw_name = cur.fetchone()[0]
    assert raw_name == "Bufete Pérez & Asociados"


def test_update_branding_unknown_tenant_raises(manager):
    """update_branding en tenant inexistente → KeyError."""
    with pytest.raises(KeyError, match="Tenant not found"):
        manager.update_branding("nonexistent-tenant", {"primary_color": "#fff"})


def test_update_license_json_serialization_includes_all_fields(manager):
    """El JSON serializado en DB contiene todas las claves de cada dict."""
    tid = manager.create_tenant("JSON Firm", "json-firm", license_type="enterprise")
    cur = manager._conn.execute(  # noqa: SLF001
        "SELECT branding_json, feature_flags_json, license_json, audit_config_json "
        "FROM tenants WHERE id = ?",
        (tid,),
    )
    row = cur.fetchone()
    branding = json.loads(row[0])
    flags = json.loads(row[1])
    lic = json.loads(row[2])
    audit = json.loads(row[3])
    assert set(branding.keys()) == {
        "primary_color", "secondary_color", "logo_url",
        "font_family", "agent_name_override",
    }
    assert set(flags.keys()) == {
        "enable_redline_docx", "enable_rag_local", "enable_citation_graph",
        "enable_precedent_board", "enable_tabular_review", "enable_marketplace",
        "max_matters", "max_agents", "max_audit_entries",
    }
    assert set(lic.keys()) == {"type", "expires_at", "monthly_price_usd", "contact_email"}
    assert set(audit.keys()) == {"audit_log_path", "retention_years"}


# ===== Singleton =====


def test_tenant_manager_singleton(strong_secrets, tmp_path, monkeypatch):
    """get_manager() devuelve el mismo singleton; reset_manager() lo resetea."""
    # Override default paths via monkeypatch on the module-level singleton
    monkeypatch.setattr(wl_module, "_manager", None)
    # Use a custom db_path by replacing the singleton with a fresh one
    custom_mgr = TenantManager(
        db_path=str(tmp_path / "single.db"),
        data_root=str(tmp_path / "tenants"),
    )
    monkeypatch.setattr(wl_module, "_manager", custom_mgr)
    m1 = wl_module.get_manager()
    m2 = wl_module.get_manager()
    assert m1 is m2
    assert m1 is custom_mgr
    wl_module.reset_manager()
    assert wl_module._manager is None  # noqa: SLF001
    custom_mgr.close()
