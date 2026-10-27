"""
AGENTS — organigrama de agentes especialistas del Despacho Jurídico.

Cada agente es un archivo markdown con YAML frontmatter (no código Python).
El loader los parsea, valida y monta sobre el ARNÉS migration (GeneralAdapter).

Patrón seguido (clean-room, de la FICHA):
- JudicialMind: agent files en markdown
- Claude-Code-Law-Firm: agents/skills/workflows YAML
- Legal-Skills-Open: SKILL.md con frontmatter
- GLAW: SKILL.md + seats con `reports_to`/`escalates_to`/`delegates_to`

Campos obligatorios en frontmatter:
    id: str                  — identificador único (kebab-case)
    name: str                — nombre display
    tier: str                — leadership | specialist | support
    reports_to: str          — id del agente al que reporta (o "nobody" para leadership)
    escalates_to: str        — id del agente al que escala (o "nobody")
    delegates_to: list[str]  — ids de agentes a los que delega
    tools: list[str]         — herramientas/capacidades que puede invocar
    minimum_human_signoff: int — firmas humanas obligatorias para acciones del agente
    practice_areas: list[str] — áreas de práctica donde actúa (civil, constitucional, laboral, ...)
"""
from albra.agents.loader import (
    AgentDefinition,
    AgentLoader,
    AgentValidationError,
)

__all__ = [
    "AgentDefinition",
    "AgentLoader",
    "AgentValidationError",
]
