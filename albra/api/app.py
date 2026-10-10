"""FastAPI app - V1.6 con auth + RBAC (P1)."""
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

app = FastAPI(
    title=AGENT_MANIFEST.name,
    version="1.6.0",
    description="Agente Base del Despacho Jurídico Digital ALBRA - V1.6 INTEGRATION COMPLETE",
)

# --- Auth security scheme ---
bearer_scheme = HTTPBearer(auto_error=False)

_agent: Any = None
_security_gate: SecurityGate | None = None


async def _get_agent():
    global _agent, _security_gate
    if _agent is None:
        _agent = get_agent()
        await _agent.boot()
        s = Settings()
        _security_gate = SecurityGate(s)
        # Wire security gate como órgano del agent
        _agent.organs["security"] = _security_gate
    return _agent, _security_gate


async def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    request: Request = None,
) -> dict[str, Any]:
    """Dependency FastAPI - autentica via Bearer token.

    Returns:
        dict con user, role, authenticated
    Raises:
        HTTPException 401 si no autenticado.
    """
    _, gate = await _get_agent()
    if not credentials:
        # Allow service identity for internal calls via X-Service-Token header
        if request:
            service_token = request.headers.get("X-Service-Token")
            if service_token and service_token == "albra-internal-service":
                return {"user": "service", "role": "admin", "authenticated": True}
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Token format: <user>:<password> - simple pero funcional para dev
    # PRODUCCIÓN: usar JWT firmado
    try:
        token = credentials.credentials
        if ":" not in token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token format: user:password",
            )
        user, password = token.split(":", 1)
        ctx = await gate.login(user, password)
        if not ctx.authenticated:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )
        return {
            "user": ctx.user,
            "role": ctx.role,
            "authenticated": True,
            "session": ctx.session,
        }
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Auth error: {e}",
        )


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

class ChatRequest(BaseModel):
    message: str
    user: str = "api_user"
    channel: str = "text"


class LoginRequest(BaseModel):
    user: str
    password: str


# --- Endpoints ---

@app.get("/")
async def root() -> dict[str, Any]:
    """Root - público (identidad)."""
    return AGENT_MANIFEST.manifest()


@app.get("/health")
async def health(auth: dict = Depends(require_permission("doctor.run"))) -> dict[str, Any]:
    agent, _ = await _get_agent()
    doc = agent.organs["doctor"]
    report = await doc.diagnose(scope="all")
    return report.as_dict()


@app.post("/chat")
async def chat(
    req: ChatRequest,
    auth: dict = Depends(require_permission("tools.invoke_low")),
) -> dict[str, Any]:
    agent, _ = await _get_agent()
    # RBAC: usar el rol del authenticated user
    return await agent.process(
        req.message,
        channel=req.channel,
        user=auth["user"],
        user_role=auth["role"],
    )


@app.get("/tools")
async def list_tools(auth: dict = Depends(require_permission("tools.invoke"))) -> list[dict[str, Any]]:
    agent, _ = await _get_agent()
    return agent.organs["tools"].list()


@app.get("/capabilities")
async def list_capabilities(auth: dict = Depends(require_permission("tools.invoke"))) -> list[dict[str, Any]]:
    agent, _ = await _get_agent()
    return agent.organs["capabilities"].list()


@app.get("/organs")
async def list_organs(auth: dict = Depends(require_permission("doctor.run"))) -> list[str]:
    agent, _ = await _get_agent()
    return list(agent.organs.keys())


@app.get("/memory/stats")
async def memory_stats(auth: dict = Depends(require_permission("memory.read"))) -> dict[str, Any]:
    agent, _ = await _get_agent()
    return agent.organs["memory"].stats()


@app.get("/audit")
async def audit_tail(
    limit: int = 50,
    auth: dict = Depends(require_permission("security.audit_read")),
) -> list[dict[str, Any]]:
    agent, _ = await _get_agent()
    return agent.organs["audit"].read(limit=limit)


@app.get("/evidence")
async def evidence_list(
    limit: int = 50,
    auth: dict = Depends(require_permission("tools.invoke")),
) -> list[dict[str, Any]]:
    agent, _ = await _get_agent()
    return agent.organs["evidence"].list(limit=limit)


@app.post("/login")
async def login(req: LoginRequest) -> dict[str, Any]:
    """Endpoint público de login - devuelve token de sesión."""
    _, gate = await _get_agent()
    ctx = await gate.login(req.user, req.password)
    if not ctx.authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    return {
        "user": ctx.user,
        "role": ctx.role,
        "session": ctx.session,
        # Para dev: token = "user:password" para usar en Bearer
        # PRODUCCIÓN: devolver JWT firmado
        "bearer_token": f"{req.user}:{req.password}",
    }
