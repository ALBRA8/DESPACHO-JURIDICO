"""
AGENT LOADER — parsea definiciones de agentes en markdown + YAML frontmatter.

Cada archivo ``albra/agents/definitions/<agent>.md`` tiene:

```markdown
---
id: intake-agent
name: INTAKE-AGENT
tier: specialist
reports_to: filing-agent
escalates_to: drafting-agent
delegates_to: []
tools:
  - research.run
  - knowledge.write
minimum_human_signoff: 0
practice_areas:
  - civil
  - constitucional
  - laboral
  - penal
  - corporativo
  - administrativo
  - familia
---

# INTAKE-AGENT

Role: Recopilar y estructurar datos del cliente para un matter nuevo.

## Responsabilidades
- ...

## Cuándo actúa
- ...
```

El loader:
1. Lee todos los ``*.md`` en ``definitions/``.
2. Parsea YAML frontmatter.
3. Valida campos obligatorios y referencias cruzadas.
4. Devuelve ``AgentDefinition`` objects.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from albra.observability.logger import get_logger


class AgentValidationError(ValueError):
    """Levantado cuando un agente definido en markdown es inválido."""


_REQUIRED_FIELDS: tuple[str, ...] = (
    "id", "name", "tier", "reports_to", "escalates_to",
    "delegates_to", "tools", "minimum_human_signoff", "practice_areas",
)

_VALID_TIERS: frozenset[str] = frozenset({"leadership", "specialist", "support"})


@dataclass
class AgentDefinition:
    """Definición de un agente parseada desde markdown + YAML frontmatter."""
    id: str
    name: str
    tier: str
    reports_to: str
    escalates_to: str
    delegates_to: list[str]
    tools: list[str]
    minimum_human_signoff: int
    practice_areas: list[str]
    body_markdown: str = ""
    file_path: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "tier": self.tier,
            "reports_to": self.reports_to,
            "escalates_to": self.escalates_to,
            "delegates_to": self.delegates_to,
            "tools": self.tools,
            "minimum_human_signoff": self.minimum_human_signoff,
            "practice_areas": self.practice_areas,
            "body_markdown_preview": self.body_markdown[:200],
            "file_path": self.file_path,
        }


def _parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Separa YAML frontmatter del body markdown.

    Formato:
        ---
        key: value
        ---
        # Body markdown
    """
    # El archivo debe empezar con --- (con o sin BOM/saltos iniciales)
    content = content.lstrip("\ufeff").lstrip()
    if not content.startswith("---"):
        return {}, content
    # Buscar el cierre del frontmatter
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", content, re.DOTALL)
    if not match:
        raise AgentValidationError(
            "Frontmatter YAML mal formado: falta cerrar con '---' después del bloque."
        )
    yaml_block, body = match.group(1), match.group(2)
    # Parse YAML manualmente (sin dependencia externa): soporta claves simples y listas
    frontmatter: dict[str, Any] = {}
    current_key: str | None = None
    for line in yaml_block.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Lista item
        if stripped.startswith("- ") and current_key is not None:
            value = stripped[2:].strip()
            # Quitar comillas
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                value = value[1:-1]
            if isinstance(frontmatter.get(current_key), list):
                frontmatter[current_key].append(value)
            else:
                frontmatter[current_key] = [value]
            continue
        # key: value
        if ":" in stripped:
            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip()
            # Quitar comillas (strings entrecomillados)
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                value = value[1:-1]
            # Sintaxis inline []: lista vacía o [a, b, c]
            if value.startswith("[") and value.endswith("]"):
                inner = value[1:-1].strip()
                if not inner:
                    frontmatter[key] = []
                    current_key = key
                    continue
                items = [s.strip() for s in inner.split(",")]
                # Quitar comillas de cada item
                items = [
                    s[1:-1] if (s.startswith('"') and s.endswith('"')) or
                    (s.startswith("'") and s.endswith("'")) else s
                    for s in items
                ]
                frontmatter[key] = items
                current_key = key
                continue
            # Sintaxis inline {}: dict vacío o {k: v}
            if value.startswith("{") and value.endswith("}"):
                # Tratamos como string metadata para V2.0 (no lo usamos en agents)
                frontmatter[key] = value
                current_key = key
                continue
            if value == "":
                # Será llenado por items subsiguientes (lista multiline)
                frontmatter[key] = []
                current_key = key
            else:
                # Tipos básicos
                if value.lower() in ("true", "false"):
                    frontmatter[key] = value.lower() == "true"
                elif value.lstrip("-").isdigit():
                    frontmatter[key] = int(value)
                else:
                    frontmatter[key] = value
                current_key = key
    return frontmatter, body


class AgentLoader:
    """Carga definiciones de agentes desde ``definitions/``.

    Usage:
        loader = AgentLoader()
        agents = loader.load_all()
        intake = loader.get("intake-agent")
    """

    def __init__(self, definitions_dir: str | None = None) -> None:
        if definitions_dir is None:
            definitions_dir = str(Path(__file__).parent / "definitions")
        self.definitions_dir = Path(definitions_dir)
        self.log = get_logger("albra.agents.loader")
        self._cache: dict[str, AgentDefinition] | None = None

    def load_all(self, *, force_reload: bool = False) -> dict[str, AgentDefinition]:
        """Carga todos los *.md de definitions/. Devuelve dict {id: AgentDefinition}."""
        if self._cache is not None and not force_reload:
            return self._cache
        if not self.definitions_dir.exists():
            self.log.warning("agents.definitions_missing", path=str(self.definitions_dir))
            self._cache = {}
            return self._cache

        agents: dict[str, AgentDefinition] = {}
        for path in sorted(self.definitions_dir.glob("*.md")):
            try:
                agent = self._load_one(path)
                agents[agent.id] = agent
                self.log.info("agents.loaded", agent_id=agent.id, file=path.name)
            except AgentValidationError as e:
                self.log.error("agents.load_failed", file=path.name, error=str(e))
                raise
        # Validar referencias cruzadas
        self._validate_cross_references(agents)
        self._cache = agents
        return agents

    def _load_one(self, path: Path) -> AgentDefinition:
        content = path.read_text(encoding="utf-8")
        frontmatter, body = _parse_frontmatter(content)

        # Validar campos obligatorios
        missing = [f for f in _REQUIRED_FIELDS if f not in frontmatter]
        if missing:
            raise AgentValidationError(
                f"Agente {path.name}: faltan campos obligatorios en frontmatter: {missing}"
            )

        # Validar tier
        tier = str(frontmatter["tier"])
        if tier not in _VALID_TIERS:
            raise AgentValidationError(
                f"Agente {path.name}: tier inválido {tier!r}. "
                f"Válidos: {sorted(_VALID_TIERS)}"
            )

        # Validar minimum_human_signoff entero ≥ 0
        mhs = int(frontmatter["minimum_human_signoff"])
        if mhs < 0:
            raise AgentValidationError(
                f"Agente {path.name}: minimum_human_signoff no puede ser negativo: {mhs}"
            )

        # delegates_to y tools deben ser listas
        delegates = frontmatter["delegates_to"]
        if not isinstance(delegates, list):
            delegates = [delegates] if delegates else []
        tools = frontmatter["tools"]
        if not isinstance(tools, list):
            tools = [tools] if tools else []
        practice = frontmatter["practice_areas"]
        if not isinstance(practice, list):
            practice = [practice] if practice else []

        return AgentDefinition(
            id=str(frontmatter["id"]),
            name=str(frontmatter["name"]),
            tier=tier,
            reports_to=str(frontmatter["reports_to"]),
            escalates_to=str(frontmatter["escalates_to"]),
            delegates_to=delegates,
            tools=tools,
            minimum_human_signoff=mhs,
            practice_areas=practice,
            body_markdown=body,
            file_path=str(path),
        )

    def _validate_cross_references(self, agents: dict[str, AgentDefinition]) -> None:
        """reports_to, escalates_to, delegates_to deben referir a agentes existentes."""
        ids = set(agents.keys()) | {"nobody"}
        for agent in agents.values():
            if agent.reports_to not in ids:
                raise AgentValidationError(
                    f"Agente {agent.id}: reports_to={agent.reports_to!r} no existe"
                )
            if agent.escalates_to not in ids:
                raise AgentValidationError(
                    f"Agente {agent.id}: escalates_to={agent.escalates_to!r} no existe"
                )
            for d in agent.delegates_to:
                if d not in ids:
                    raise AgentValidationError(
                        f"Agente {agent.id}: delegates_to={d!r} no existe"
                    )
        # Al menos un leadership tier
        if not any(a.tier == "leadership" for a in agents.values()):
            raise AgentValidationError(
                "El organigrama debe tener al menos un agente tier=leadership"
            )

    def get(self, agent_id: str) -> AgentDefinition | None:
        agents = self.load_all()
        return agents.get(agent_id)

    def list_ids(self) -> list[str]:
        return sorted(self.load_all().keys())

    def organigrama(self) -> list[dict[str, Any]]:
        """Devuelve el organigrama: lista de agents con su tier y reports_to."""
        agents = self.load_all()
        return [a.as_dict() for a in agents.values()]

    def reload(self) -> dict[str, AgentDefinition]:
        """Fuerza recarga desde disco."""
        self._cache = None
        return self.load_all(force_reload=True)
