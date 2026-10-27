"""
PLAYBOOK LOADER — parser markdown + YAML frontmatter para playbooks.

Reutiliza el parser del AgentLoader (albra/agents/loader._parse_frontmatter).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from albra.agents.loader import _parse_frontmatter
from albra.observability.logger import get_logger


class PlaybookValidationError(ValueError):
    """Levantado cuando un playbook markdown es inválido."""


_REQUIRED_FIELDS: tuple[str, ...] = (
    "practice_area",
    "typical_matter_types",
    "workflow_states",
    "required_documents",
    "deadline_types",
    "citation_corpus",
    "red_flags",
)


@dataclass
class Playbook:
    """Definición de un playbook parseada desde markdown."""
    practice_area: str
    typical_matter_types: list[str]
    workflow_states: list[str]
    required_documents: list[str]
    deadline_types: list[str]
    citation_corpus: list[str]
    red_flags: list[str]
    body_markdown: str = ""
    file_path: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "practice_area": self.practice_area,
            "typical_matter_types": self.typical_matter_types,
            "workflow_states": self.workflow_states,
            "required_documents": self.required_documents,
            "deadline_types": self.deadline_types,
            "citation_corpus": self.citation_corpus,
            "red_flags": self.red_flags,
            "body_markdown_preview": self.body_markdown[:300],
            "file_path": self.file_path,
        }


class PlaybookLoader:
    """Carga playbooks desde definitions/."""

    def __init__(self, definitions_dir: str | None = None) -> None:
        if definitions_dir is None:
            definitions_dir = str(Path(__file__).parent / "definitions")
        self.definitions_dir = Path(definitions_dir)
        self.log = get_logger("albra.playbooks.loader")
        self._cache: dict[str, Playbook] | None = None

    def load_all(self, *, force_reload: bool = False) -> dict[str, Playbook]:
        if self._cache is not None and not force_reload:
            return self._cache
        if not self.definitions_dir.exists():
            self.log.warning("playbooks.definitions_missing", path=str(self.definitions_dir))
            self._cache = {}
            return self._cache

        playbooks: dict[str, Playbook] = {}
        for path in sorted(self.definitions_dir.glob("*.md")):
            try:
                pb = self._load_one(path)
                playbooks[pb.practice_area] = pb
                self.log.info("playbooks.loaded", practice_area=pb.practice_area, file=path.name)
            except PlaybookValidationError as e:
                self.log.error("playbooks.load_failed", file=path.name, error=str(e))
                raise
        self._cache = playbooks
        return playbooks

    def _load_one(self, path: Path) -> Playbook:
        content = path.read_text(encoding="utf-8")
        frontmatter, body = _parse_frontmatter(content)

        missing = [f for f in _REQUIRED_FIELDS if f not in frontmatter]
        if missing:
            raise PlaybookValidationError(
                f"Playbook {path.name}: faltan campos: {missing}"
            )

        def _as_list(v: Any) -> list[str]:
            if isinstance(v, list):
                return v
            return [v] if v else []

        return Playbook(
            practice_area=str(frontmatter["practice_area"]),
            typical_matter_types=_as_list(frontmatter["typical_matter_types"]),
            workflow_states=_as_list(frontmatter["workflow_states"]),
            required_documents=_as_list(frontmatter["required_documents"]),
            deadline_types=_as_list(frontmatter["deadline_types"]),
            citation_corpus=_as_list(frontmatter["citation_corpus"]),
            red_flags=_as_list(frontmatter["red_flags"]),
            body_markdown=body,
            file_path=str(path),
        )

    def get(self, practice_area: str) -> Playbook | None:
        return self.load_all().get(practice_area)

    def list_areas(self) -> list[str]:
        return sorted(self.load_all().keys())

    def reload(self) -> dict[str, Playbook]:
        self._cache = None
        return self.load_all(force_reload=True)
