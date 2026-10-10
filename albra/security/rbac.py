"""
RBAC GRANULAR ALBRA - permisos <recurso>.<acción>.

Inspirado en CRM-ALBRA/src/lib/rbac.ts.

Roles:
- owner    → control total del despacho
- admin    → gestión operativa, sin tocar configuración crítica
- abogado  → expedientes, demandas, comunicaciones con clientes
- asistente → tareas operativas, lectura
- externo  → solo observación
- anon     → solo chat básico

Patrón: <recurso>.<acción> con wildcard `.*`
Ejemplos: expedientes.read, expedientes.write, clients.write, settings.*
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Role:
    name: str
    description: str
    permissions: tuple[str, ...] = ()
    inherits: str | None = None  # hereda permisos de otro rol

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "permissions": list(self.permissions),
            "inherits": self.inherits,
        }


# Catálogo de permisos por dominio jurídico
PERMISSIONS_CATALOG: tuple[str, ...] = (
    # Expedientes
    "expedientes.read",
    "expedientes.write",
    "expedientes.delete",
    "expedientes.export",
    # Clientes
    "clients.read",
    "clients.write",
    "clients.history",
    # Demandas
    "demandas.read",
    "demandas.write",
    "demandas.sign",
    "demandas.file",
    # Comunicaciones
    "comms.send",
    "comms.read",
    "comms.send_external",
    # Documentos
    "documents.read",
    "documents.write",
    "documents.generate",
    "documents.sign",
    # Investigación
    "research.run",
    "research.web",
    # Conocimiento
    "knowledge.read",
    "knowledge.write",
    "knowledge.validate",
    # Tools
    "tools.invoke",
    "tools.invoke_low",
    "tools.invoke_medium",
    "tools.invoke_high",
    # Configuración
    "settings.read",
    "settings.write",
    "settings.*",
    # Seguridad
    "security.users",
    "security.permissions",
    "security.audit_read",
    # Doctor
    "doctor.run",
    "doctor.recover",
    # Autonomía
    "autonomy.set_level",
    "autonomy.engage_kill",
    "autonomy.release_kill",
    # Memoria
    "memory.read",
    "memory.write",
    "memory.purge",
    # MCP
    "mcp.invoke",
    "mcp.register_server",
)


ROLES: dict[str, Role] = {
    "owner": Role(
        name="owner",
        description="Control total del despacho",
        permissions=("settings.*", "security.*", "*"),  # owner = todo
    ),
    "admin": Role(
        name="admin",
        description="Gestión operativa completa sin tocar config crítica",
        permissions=(
            "expedientes.*", "clients.*", "demandas.*", "documents.*",
            "research.*", "knowledge.*", "comms.*",
            "tools.invoke", "tools.invoke_low", "tools.invoke_medium", "tools.invoke_high",
            "settings.read", "memory.*", "doctor.*", "mcp.*",
        ),
    ),
    "abogado": Role(
        name="abogado",
        description="Trabajo con expedientes y demandas",
        permissions=(
            "expedientes.read", "expedientes.write",
            "clients.read", "clients.write", "clients.history",
            "demandas.read", "demandas.write", "demandas.sign",
            "documents.read", "documents.write", "documents.generate",
            "comms.read", "comms.send_external",
            "research.run", "research.web",
            "knowledge.read",
            "tools.invoke", "tools.invoke_low", "tools.invoke_medium",
            "memory.read", "memory.write",
            "mcp.invoke", "doctor.run",
        ),
    ),
    "asistente": Role(
        name="asistente",
        description="Tareas operativas, lectura",
        permissions=(
            "expedientes.read", "clients.read",
            "documents.read",
            "comms.read",
            "research.run",
            "knowledge.read",
            "tools.invoke", "tools.invoke_low",
            "memory.read",
            "doctor.run",
        ),
    ),
    "externo": Role(
        name="externo",
        description="Solo observación",
        permissions=(
            "expedientes.read", "documents.read", "knowledge.read",
            "doctor.run",
        ),
    ),
    "anon": Role(
        name="anon",
        description="Usuario anónimo - solo chat básico",
        permissions=("tools.invoke_low",),
    ),
}


def get_role(name: str) -> Role | None:
    return ROLES.get(name)


def list_roles() -> list[dict[str, Any]]:
    return [r.as_dict() for r in ROLES.values()]


def has_permission(role_name: str, permission: str) -> bool:
    """Verifica si un rol tiene un permiso (con wildcard * y .*)"""
    role = get_role(role_name)
    if not role:
        return False
    perms = _resolve_permissions(role)
    # Match exacto
    if permission in perms:
        return True
    # Match wildcard de recurso: "expedientes.*" matches "expedientes.read"
    resource = permission.split(".")[0] if "." in permission else permission
    if f"{resource}.*" in perms:
        return True
    # Match wildcard global "*"
    if "*" in perms:
        return True
    return False


def _resolve_permissions(role: Role) -> set[str]:
    """Resuelve permisos heredados."""
    perms = set(role.permissions)
    if role.inherits:
        parent = get_role(role.inherits)
        if parent:
            perms.update(_resolve_permissions(parent))
    return perms


def permissions_for(role_name: str) -> list[str]:
    role = get_role(role_name)
    if not role:
        return []
    return sorted(_resolve_permissions(role))
