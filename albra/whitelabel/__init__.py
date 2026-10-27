"""
WHITE-LABEL PLATFORM — permite a otros despachos colombianos licenciar
ALBRA bajo su propia marca.

Inspiración clean-room: case.dev (white-label platform con monthly
minimum or annual commitment), LawVu (Microsoft sensitivity labels
integration for tenant isolation), Gotham (data residency garantizada
en el país del cliente).

V2.5-B: tenant management + branding config + feature flags per tenant.
V2.5+: Stripe/USDC billing integration + SaaS deployment.

Cada tenant:
- id: UUID
- name: nombre display del despacho (p. ej. "Bufete Pérez & Asociados")
- slug: kebab-case para URLs (p. ej. "perez-asociados")
- branding: {primary_color, secondary_color, logo_url, font_family,
             agent_name_override (p. ej. "AGENTE PEREZ" en vez de
             "AGENTE-GENERAL")}
- feature_flags: {enable_redline_docx: bool, enable_rag_local: bool,
                   enable_citation_graph: bool, enable_precedent_board: bool,
                   enable_tabular_review: bool, enable_marketplace: bool,
                   max_matters: int, max_agents: int, max_audit_entries: int}
- license: {type: trial | pro | enterprise, expires_at: ISO date,
            monthly_price_usd: float, contact_email: str}
- audit_config: {audit_log_path: str (per-tenant), retention_years: int}
- created_at: ISO timestamp

API:
- create_tenant(name, slug, license_type='trial') -> str
- get_tenant(tenant_id) -> Tenant | None
- get_tenant_by_slug(slug) -> Tenant | None
- list_tenants() -> list[Tenant]
- update_branding(tenant_id, branding) -> Tenant
- update_feature_flags(tenant_id, flags) -> Tenant
- update_license(tenant_id, license) -> Tenant
- is_feature_enabled(tenant_id, flag) -> bool
- is_license_valid(tenant_id) -> bool
- delete_tenant(tenant_id) -> bool
- stats() -> dict

Storage: SQLite local en data/tenants.db (multi-tenant safe).

Tenant isolation: cada tenant tiene su propio matter_data_dir
(data/tenants/<tenant_id>/matters/) y audit log path.
"""
from albra.whitelabel.tenant import (
    Tenant,
    TenantManager,
    TenantValidationError,
    get_manager,
    reset_manager,
)

__all__ = [
    "Tenant",
    "TenantManager",
    "TenantValidationError",
    "get_manager",
    "reset_manager",
]
