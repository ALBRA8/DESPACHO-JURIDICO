"""
Harness API — endpoints del arnés para inspección externa.

Monta el arnés ALBRA y expone:
- list-bridges
- list-skills
- list-knowledge
- knowledge-health
- execute-skill
- agent-execute
- agent-health
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.bootstrap import bootstrap

router = APIRouter(prefix="/harness", tags=["harness"])

# Singleton context (initialized lazily)
_context: Optional[Any] = None


def get_context():
    """Obtiene o inicializa el contexto del arnés."""
    global _context
    if _context is None:
        _context = bootstrap()
    return _context


class HarnessRequest(BaseModel):
    operation: str
    params: Dict[str, Any] = {}


@router.post("")
async def harness_endpoint(req: HarnessRequest):
    """Endpoint único del arnés — opera por dispatch de operation."""
    ctx = get_context()

    try:
        if req.operation == "list-bridges":
            return {"bridges": ctx.bridges.list()}

        elif req.operation == "list-skills":
            return {"skills": ctx.skills.list()}

        elif req.operation == "list-knowledge":
            return {"knowledge": ctx.knowledge.list()}

        elif req.operation == "knowledge-health":
            return {"health": ctx.knowledge.health_check()}

        elif req.operation == "execute-skill":
            from src.harness.types import SkillContext
            skill_ctx = SkillContext(
                bridges=ctx.bridges,
                knowledge=ctx.knowledge,
                agent=None,  # agent not in context directly
                params=req.params.get("params", {}),
            )
            result = await ctx.skills.execute(
                req.params.get("skillId", ""),
                req.params.get("skillOperation", ""),
                skill_ctx,
            )
            return {"success": result.success, "data": result.data, "error": result.error}

        elif req.operation == "query-knowledge":
            module = ctx.knowledge.get(req.params.get("moduleId", ""))
            if not module:
                raise HTTPException(404, f"Knowledge module not found: {req.params.get('moduleId', '')}")
            return {"success": True, "data": module.get_content()}

        else:
            raise HTTPException(400, f"Unknown operation: {req.operation}")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/bridges")
async def list_bridges():
    ctx = get_context()
    return {"bridges": ctx.bridges.list()}


@router.get("/skills")
async def list_skills():
    ctx = get_context()
    return {"skills": ctx.skills.list()}


@router.get("/knowledge")
async def list_knowledge():
    ctx = get_context()
    return {"knowledge": ctx.knowledge.list()}


@router.get("/knowledge/health")
async def knowledge_health():
    ctx = get_context()
    return {"health": ctx.knowledge.health_check()}


@router.get("/knowledge/{module_id}")
async def get_knowledge_module(module_id: str):
    ctx = get_context()
    module = ctx.knowledge.get(module_id)
    if not module:
        raise HTTPException(404, f"Knowledge module not found: {module_id}")
    return {
        "id": module.id,
        "name": module.name,
        "category": module.category,
        "version": module.version,
        "content": module.get_content(),
    }
