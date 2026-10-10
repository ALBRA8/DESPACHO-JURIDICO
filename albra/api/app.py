"""FastAPI app - endpoints básicos."""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from albra.identity.agent import get_agent
from albra.identity.manifest import AGENT_MANIFEST

app = FastAPI(
    title=AGENT_MANIFEST.name,
    version=AGENT_MANIFEST.version,
    description="Agente Base del Despacho Jurídico Digital ALBRA",
)

_agent = None


async def _get_agent():
    global _agent
    if _agent is None:
        _agent = get_agent()
        await _agent.boot()
    return _agent


class ChatRequest(BaseModel):
    message: str
    user: str = "api_user"
    channel: str = "text"


@app.get("/")
async def root() -> dict[str, Any]:
    return AGENT_MANIFEST.manifest()


@app.get("/health")
async def health() -> dict[str, Any]:
    agent = await _get_agent()
    doc = agent.organs["doctor"]
    report = await doc.diagnose(scope="all")
    return report.as_dict()


@app.post("/chat")
async def chat(req: ChatRequest) -> dict[str, Any]:
    agent = await _get_agent()
    return await agent.process(req.message, channel=req.channel, user=req.user)


@app.get("/tools")
async def list_tools() -> list[dict[str, Any]]:
    agent = await _get_agent()
    return agent.organs["tools"].list()


@app.get("/capabilities")
async def list_capabilities() -> list[dict[str, Any]]:
    agent = await _get_agent()
    return agent.organs["capabilities"].list()


@app.get("/organs")
async def list_organs() -> list[str]:
    agent = await _get_agent()
    return list(agent.organs.keys())


@app.get("/memory/stats")
async def memory_stats() -> dict[str, Any]:
    agent = await _get_agent()
    return agent.organs["memory"].stats()


@app.get("/audit")
async def audit_tail(limit: int = 50) -> list[dict[str, Any]]:
    agent = await _get_agent()
    return agent.organs["audit"].read(limit=limit)


@app.get("/evidence")
async def evidence_list(limit: int = 50) -> list[dict[str, Any]]:
    agent = await _get_agent()
    return agent.organs["evidence"].list(limit=limit)
