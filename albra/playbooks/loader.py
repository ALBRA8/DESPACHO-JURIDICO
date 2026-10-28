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
    # V2.5-H3 enforcement controls (defaults so stock playbooks pass).
    # Tests / runtime can override these to verify validate_enforcement
    # catches drift (e.g. construct a Playbook with rbac_required=False).
    rbac_required: bool = True
    citation_audit_required: bool = True
    approval_required: bool = True
    audit_required: bool = True

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
            "rbac_required": self.rbac_required,
            "citation_audit_required": self.citation_audit_required,
            "approval_required": self.approval_required,
            "audit_required": self.audit_required,
        }

    def has_sensitive_actions(self) -> bool:
        """Heuristic: a playbook is 'sensitive' if it has an approval
        workflow state, red flags, or required documents that must be
        reviewed before filing.

        All 5 stock playbooks satisfy this (they all include
        'EN-ESPERA-DE-APROBACIÓN' in workflow_states), so they require
        approval_required=True.
        """
        if any("APROBACIÓN" in s.upper() for s in self.workflow_states):
            return True
        if self.red_flags:
            return True
        if self.required_documents:
            return True
        return False


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

    # ===== V2.5-H3 enforcement =====

    def validate_enforcement(self, playbook: Playbook) -> dict[str, Any]:
        """Check that a playbook respects ALBRA's control invariants.

        Returns:
            {
                "rbac_required": bool,
                "citation_audit_required": bool,
                "approval_required": bool,
                "audit_required": bool,
                "all_enforced": bool,
            }

        Invariants enforced:
        - rbac_required MUST be True (every playbook gates actions by role).
        - audit_required MUST be True (every playbook writes an audit trail).
        - approval_required MUST be True when the playbook has sensitive
          actions (approval workflow state / red_flags / required_documents).
        - citation_audit_required is reported but not enforced as a hard
          invariant — some playbooks may legitimately skip the citation
          audit (e.g. pure intake). It's still surfaced so callers know
          the playbook's posture.
        """
        sensitive = playbook.has_sensitive_actions()
        rbac_required = bool(playbook.rbac_required)
        audit_required = bool(playbook.audit_required)
        citation_audit_required = bool(playbook.citation_audit_required)
        # If the playbook is sensitive, approval MUST be required.
        # If the playbook is NOT sensitive, approval_required can be either
        # True or False (the caller's choice) — we still report the value.
        approval_required = bool(playbook.approval_required)
        approval_satisfied = (not sensitive) or approval_required
        all_enforced = rbac_required and audit_required and approval_satisfied
        return {
            "rbac_required": rbac_required,
            "citation_audit_required": citation_audit_required,
            "approval_required": approval_required,
            "audit_required": audit_required,
            "all_enforced": all_enforced,
        }

    def validate_all(self) -> dict[str, dict[str, Any]]:
        """Validate every loaded playbook. Returns dict keyed by practice_area."""
        return {
            area: self.validate_enforcement(pb)
            for area, pb in self.load_all().items()
        }
