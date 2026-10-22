"""
Knowledge Registry — conocimiento del dominio ALBRA.

El conocimiento jurídico vive AQUÍ, no en el agente.
Si el agente se va, el conocimiento se queda.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class IKnowledgeModule(ABC):
    """Interfaz que todo módulo de conocimiento debe implementar."""

    @property
    @abstractmethod
    def id(self) -> str: ...

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def category(self) -> str: ...

    @property
    @abstractmethod
    def version(self) -> str: ...

    @abstractmethod
    def get_content(self) -> Dict[str, Any]: ...

    @abstractmethod
    def validate(self) -> bool: ...


class KnowledgeRegistry:
    """Registry de conocimiento del dominio."""

    def __init__(self) -> None:
        self._modules: Dict[str, IKnowledgeModule] = {}

    def register(self, module: IKnowledgeModule) -> None:
        self._modules[module.id] = module

    def get(self, module_id: str) -> Optional[IKnowledgeModule]:
        return self._modules.get(module_id)

    def list(self) -> List[Dict[str, str]]:
        return [
            {"id": m.id, "name": m.name, "category": m.category}
            for m in self._modules.values()
        ]

    def get_by_category(self, category: str) -> List[IKnowledgeModule]:
        return [m for m in self._modules.values() if m.category == category]

    def health_check(self) -> Dict[str, Any]:
        invalid: List[str] = []
        valid = 0
        for m in self._modules.values():
            if m.validate():
                valid += 1
            else:
                invalid.append(m.id)
        return {"total": len(self._modules), "valid": valid, "invalid": invalid}


# ============================================================
# CONOCIMIENTO DEL DOMINIO ALBRA — REGISTRAR AQUÍ
# ============================================================

class LegalSchemasKnowledge(IKnowledgeModule):
    """Schemas jurídicos colombianos (Norm, Article, Jurisprudence, etc.)."""

    @property
    def id(self) -> str:
        return "legal-schemas"

    @property
    def name(self) -> str:
        return "Legal Schemas Colombia"

    @property
    def category(self) -> str:
        return "domain-specific"

    @property
    def version(self) -> str:
        return "1.0.0"

    def get_content(self) -> Dict[str, Any]:
        from albra.knowledge.schemas import (
            COLOMBIA_AUTHORITIES,
            DOCUMENT_TYPES,
            TIER_LABELS,
            VALIDITY_STATUS,
            SourceTier,
        )
        return {
            "document_types": list(DOCUMENT_TYPES),
            "validity_status": list(VALIDITY_STATUS),
            "authorities": list(COLOMBIA_AUTHORITIES),
            "source_tiers": {t.name: t.value for t in SourceTier},
            "tier_labels": {t.name: label for t, label in TIER_LABELS.items()},
        }

    def validate(self) -> bool:
        return True


class LegalSourcesKnowledge(IKnowledgeModule):
    """Fuentes oficiales colombianas catalogadas."""

    @property
    def id(self) -> str:
        return "legal-sources"

    @property
    def name(self) -> str:
        return "Legal Sources Colombia"

    @property
    def category(self) -> str:
        return "domain-specific"

    @property
    def version(self) -> str:
        return "1.0.0"

    def get_content(self) -> Dict[str, Any]:
        from albra.knowledge.sources import COLOMBIA_OFFICIAL_SOURCES
        return {
            s.id: {
                "name": s.name,
                "url": s.url,
                "tier": s.tier.name,
                "authority": s.authority,
                "enabled": s.enabled,
            }
            for s in COLOMBIA_OFFICIAL_SOURCES.values()
        }

    def validate(self) -> bool:
        return True


class LegalTemporalKnowledge(IKnowledgeModule):
    """Modelo temporal jurídico (vigencia, derogación, versiones)."""

    @property
    def id(self) -> str:
        return "legal-temporal"

    @property
    def name(self) -> str:
        return "Legal Temporal Model"

    @property
    def category(self) -> str:
        return "domain-specific"

    @property
    def version(self) -> str:
        return "1.0.0"

    def get_content(self) -> Dict[str, Any]:
        from albra.knowledge.temporal import VALIDITY_STATUS
        return {
            "validity_status": list(VALIDITY_STATUS),
            "query_types": ["current", "historical", "as_of", "at_publication", "any"],
        }

    def validate(self) -> bool:
        return True


class CorpusPilotKnowledge(IKnowledgeModule):
    """Corpus piloto real ingerido (Constitución, Ley 100, Ley 80)."""

    @property
    def id(self) -> str:
        return "corpus-pilot"

    @property
    def name(self) -> str:
        return "Corpus Pilot V1.1 Real"

    @property
    def category(self) -> str:
        return "domain-specific"

    @property
    def version(self) -> str:
        return "1.1.0"

    def get_content(self) -> Dict[str, Any]:
        from albra.knowledge.colombia.corpus_pilot.real_corpus_v11 import ALL_DOCUMENTS
        return {
            "documents": [
                {
                    "source_id": doc["source_id"],
                    "title": doc.get("title", ""),
                    "number": doc.get("number", ""),
                    "jurisdiction": doc.get("jurisdiction", "CO"),
                    "document_type": doc["document_type"],
                    "articles_count": len(doc.get("articles", [])),
                    "status": doc.get("status", "vigente"),
                }
                for _, doc in ALL_DOCUMENTS
            ],
            "total_documents": len(ALL_DOCUMENTS),
            "total_articles": sum(len(doc.get("articles", [])) for _, doc in ALL_DOCUMENTS),
        }

    def validate(self) -> bool:
        try:
            from albra.knowledge.colombia.corpus_pilot.real_corpus_v11 import ALL_DOCUMENTS
            return len(ALL_DOCUMENTS) > 0
        except ImportError:
            return False


class FirewallPoliciesKnowledge(IKnowledgeModule):
    """Políticas del Action Firewall jurídico."""

    @property
    def id(self) -> str:
        return "firewall-policies"

    @property
    def name(self) -> str:
        return "Action Firewall Policies"

    @property
    def category(self) -> str:
        return "validation"

    @property
    def version(self) -> str:
        return "1.0.0"

    def get_content(self) -> Dict[str, Any]:
        from albra.security.firewall.policy import FIREWALL_POLICIES
        return {
            a: {
                "risk": p.risk,
                "requires_hitl": p.requires_hitl,
                "kill_switch": p.kill_switch,
                "allowed_roles": list(p.allowed_roles),
                "description": p.description,
            }
            for a, p in FIREWALL_POLICIES.items()
        }

    def validate(self) -> bool:
        return True


class LegalSOPsKnowledge(IKnowledgeModule):
    """SOPs jurídicos (demanda civil, contestación)."""

    @property
    def id(self) -> str:
        return "legal-sops"

    @property
    def name(self) -> str:
        return "Legal SOPs"

    @property
    def category(self) -> str:
        return "orchestration"

    @property
    def version(self) -> str:
        return "1.0.0"

    def get_content(self) -> Dict[str, Any]:
        from albra.workflows.sops import SOP_CATALOG
        return {
            name: {
                "description": sop.description,
                "jurisdiction": sop.jurisdiction,
                "steps": len(sop.steps),
                "hitl_steps": sum(1 for s in sop.steps if s.requires_hitl),
            }
            for name, sop in SOP_CATALOG.items()
        }

    def validate(self) -> bool:
        return True


class SpecialistsKnowledge(IKnowledgeModule):
    """Catálogo de especialistas jurídicos colombianos."""

    @property
    def id(self) -> str:
        return "specialists"

    @property
    def name(self) -> str:
        return "Legal Specialists Catalog"

    @property
    def category(self) -> str:
        return "domain-specific"

    @property
    def version(self) -> str:
        return "1.0.0"

    def get_content(self) -> Dict[str, Any]:
        from albra.knowledge.specialists import SPECIALIST_CATALOG
        return {
            area: {
                "codename": s.codename,
                "description": s.description,
                "default_autonomy_ceiling": s.default_autonomy_ceiling,
            }
            for area, s in SPECIALIST_CATALOG.items()
        }

    def validate(self) -> bool:
        return True


def register_builtin_knowledge(registry: KnowledgeRegistry) -> None:
    """Registrar todo el conocimiento del dominio ALBRA en el arnés."""
    registry.register(LegalSchemasKnowledge())
    registry.register(LegalSourcesKnowledge())
    registry.register(LegalTemporalKnowledge())
    registry.register(CorpusPilotKnowledge())
    registry.register(FirewallPoliciesKnowledge())
    registry.register(LegalSOPsKnowledge())
    registry.register(SpecialistsKnowledge())
