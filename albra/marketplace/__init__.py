"""
MARKETPLACE — catálogo público de skills de ALBRA consumibles vía MCP.

Inspiración clean-room:
- Agent Skills for Legal (969+ skills, Find→Copy→Use, MCP integration)
- case.dev (880+ portable skills, se van con el firm)

V2.5-A: registry local en memoria (pure Python). V2.5+: HTTP server público
con OAuth + rate limiting. Las skills indexan las 10 tools del McpServer
público V2.3-B como unidades descubribles.

Cada skill:
- id: kebab-case único
- name: display name
- description: qué hace
- category: drafting | review | research | analysis | compliance | deadline
- practice_areas: list[str] (civil, laboral, constitucional, ...)
- mcp_tool_name: tool MCP que la expone (uno de los 10 de V2.3-B)
- input_schema: dict JSON schema
- output_type: str (dict | list | str)
- version: str (semver, default "1.0.0")
- author: str (default "ALBRA")
- license: str (default "Apache-2.0")
- tags: list[str]
- examples: list[dict] (input → output samples)

Bootstrap automático: 5 agentes (V2.0) + 5 playbooks (V2.2-D) + 5 tools
avanzadas (CitationAuditor, LocalRAG, DeadlineGuard, AgenticCitator,
PrecedentBoard) = 15 skills pre-registradas.
"""
from albra.marketplace.skills import (
    Skill,
    SkillsMarketplace,
    SkillValidationError,
    get_marketplace,
    reset_marketplace,
)

__all__ = [
    "Skill",
    "SkillValidationError",
    "SkillsMarketplace",
    "get_marketplace",
    "reset_marketplace",
]
