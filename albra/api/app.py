"""FastAPI app - V1.6 FINAL con JWT HMAC auth (sin hardcoded secrets).

Pipeline:
HTTP → Authentication (JWT) → Identity → RBAC → Policy → ExecutionGuard → Agent

NO hardcoded service tokens.
NO user:password como bearer.
Token JWT firmado con ALBRA_JWT_SECRET (configuración externa).
"""
from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from albra.config.settings import Settings
from albra.identity.agent import get_agent
from albra.identity.manifest import AGENT_MANIFEST
from albra.security.auth import SecurityGate
from albra.security.rbac import has_permission
from albra.security.tokens import issue_token, verify_token

app = FastAPI(
    title=AGENT_MANIFEST.name,
    version="1.6.0",
    description="Agente Base del Despacho Jurídico Digital ALBRA - V1.6 INTEGRATION COMPLETE",
)

# --- Auth security scheme ---
bearer_scheme = HTTPBearer(auto_error=False)

_agent: Any = None
_security_gate: SecurityGate | None = None
_settings: Settings | None = None


async def _get_agent():
    global _agent, _security_gate, _settings
    if _agent is None:
        _agent = get_agent()
        await _agent.boot()
        _settings = Settings()
        _security_gate = SecurityGate(_settings)
        _agent.organs["security"] = _security_gate
    return _agent, _security_gate, _settings


async def require_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any]:
    """Dependency FastAPI - autentica via JWT Bearer token.

    SIN hardcoded service tokens. SIN user:password.
    Solo JWT firmado con ALBRA_JWT_SECRET.

    Returns:
        dict con user, role, authenticated
    Raises:
        HTTPException 401 si no autenticado.
    """
    _, gate, _ = await _get_agent()
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer JWT token required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    payload = verify_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {
        "user": payload["sub"],
        "role": payload["role"],
        "authenticated": True,
        "session": f"jwt-{payload['iat']}",
        "token_payload": payload,
    }


def require_permission(permission: str):
    """Dependency factory - verifica permiso RBAC."""
    async def dep(auth: dict = Depends(require_auth)) -> dict:
        if not has_permission(auth["role"], permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: requires '{permission}', role='{auth['role']}'",
            )
        return auth
    return dep


# --- Models ---

class LoginRequest(BaseModel):
    user: str
    password: str


class ChatRequest(BaseModel):
    message: str
    user: str = "api_user"
    channel: str = "text"


# --- Endpoints ---

@app.get("/")
async def root() -> dict[str, Any]:
    """Root - público (identidad)."""
    return AGENT_MANIFEST.manifest()


@app.get("/health")
async def health(auth: dict = Depends(require_permission("doctor.run"))) -> dict[str, Any]:
    agent, _, _ = await _get_agent()
    doc = agent.organs["doctor"]
    report = await doc.diagnose(scope="all")
    return report.as_dict()


@app.post("/chat")
async def chat(
    req: ChatRequest,
    auth: dict = Depends(require_permission("tools.invoke_low")),
) -> dict[str, Any]:
    agent, _, _ = await _get_agent()
    return await agent.process(
        req.message,
        channel=req.channel,
        user=auth["user"],
        user_role=auth["role"],
    )


@app.get("/tools")
async def list_tools(auth: dict = Depends(require_permission("tools.invoke"))) -> list[dict[str, Any]]:
    agent, _, _ = await _get_agent()
    return agent.organs["tools"].list()


@app.get("/capabilities")
async def list_capabilities(auth: dict = Depends(require_permission("tools.invoke"))) -> list[dict[str, Any]]:
    agent, _, _ = await _get_agent()
    return agent.organs["capabilities"].list()


@app.get("/organs")
async def list_organs(auth: dict = Depends(require_permission("doctor.run"))) -> list[str]:
    agent, _, _ = await _get_agent()
    return list(agent.organs.keys())


@app.get("/memory/stats")
async def memory_stats(auth: dict = Depends(require_permission("memory.read"))) -> dict[str, Any]:
    agent, _, _ = await _get_agent()
    return agent.organs["memory"].stats()


@app.get("/audit")
async def audit_tail(
    limit: int = 50,
    auth: dict = Depends(require_permission("security.audit_read")),
) -> list[dict[str, Any]]:
    agent, _, _ = await _get_agent()
    return agent.organs["audit"].read(limit=limit)


@app.get("/evidence")
async def evidence_list(
    limit: int = 50,
    auth: dict = Depends(require_permission("tools.invoke")),
) -> list[dict[str, Any]]:
    agent, _, _ = await _get_agent()
    return agent.organs["evidence"].list(limit=limit)


@app.post("/login")
async def login(req: LoginRequest) -> dict[str, Any]:
    """Endpoint público de login - devuelve JWT firmado tras auth real."""
    _, gate, _ = await _get_agent()
    ctx = await gate.login(req.user, req.password)
    if not ctx.authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    # Emite JWT firmado con ALBRA_JWT_SECRET
    token = issue_token(
        subject=ctx.user,
        role=ctx.role,
        extra_claims={"session": ctx.session},
    )
    return {
        "user": ctx.user,
        "role": ctx.role,
        "session": ctx.session,
        "token": token,
        "token_type": "Bearer",
        "expires_in": 86400,
    }
