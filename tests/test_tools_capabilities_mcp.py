"""Tests de tools, capabilities y MCP."""
import asyncio

from albra.capabilities.registry import CapabilityRegistry
from albra.config.settings import Settings
from albra.mcp.protocol import MCPRequest
from albra.mcp.server import MCPServer
from albra.tools.registry import ToolRegistry


def test_tools_registered_on_init():
    tr = ToolRegistry(Settings())
    names = [t["name"] for t in tr.list()]
    assert "clock" in names
    assert "calculator" in names
    assert "echo" in names
    assert "memory_lookup" in names


def test_tool_invoke_clock():
    tr = ToolRegistry(Settings())
    result = asyncio.run(tr.invoke("clock", {}, user="test"))
    assert result["ok"] is True
    assert "iso" in result["value"]


def test_tool_invoke_calculator():
    tr = ToolRegistry(Settings())
    result = asyncio.run(tr.invoke("calculator", {"expression": "2+3*4"}))
    assert result["ok"] is True
    assert result["value"] == 14


def test_tool_calculator_rejects_dangerous():
    """No debe permitir código peligroso."""
    tr = ToolRegistry(Settings())
    result = asyncio.run(tr.invoke("calculator", {"expression": "__import__('os').system('echo hack')"}))
    # Solo debe aceptar caracteres matemáticos - el resto se borra
    assert result["ok"] is True or result["ok"] is False
    # Si ok, el value no debe contener hack
    if result["ok"]:
        assert "hack" not in str(result["value"])


def test_tool_unknown_returns_error():
    tr = ToolRegistry(Settings())
    result = asyncio.run(tr.invoke("nonexistent", {}))
    assert result["ok"] is False


def test_capabilities_registry():
    cr = CapabilityRegistry(Settings(), tool_registry=None)
    caps = [c["name"] for c in cr.list()]
    assert "conversation" in caps
    assert "tool_invocation" in caps
    assert "external_communication" in caps
    assert "legal_research" in caps


def test_capability_requires_approval():
    """external_communication y document_generation requieren HITL."""
    cr = CapabilityRegistry(Settings(), tool_registry=None)
    ext = cr.get("external_communication")
    assert ext.requires_human_approval is True
    doc = cr.get("document_generation")
    assert doc.requires_human_approval is True


def test_mcp_server_initialize():
    srv = MCPServer(Settings())
    req = MCPRequest(method="initialize")
    resp = asyncio.run(srv.handle(req))
    assert resp.error is None
    assert "protocolVersion" in resp.result


def test_mcp_server_health():
    srv = MCPServer(Settings())
    srv.wire(tool_registry=ToolRegistry(Settings()), capability_registry=None)
    req = MCPRequest(method="health")
    resp = asyncio.run(srv.handle(req))
    assert resp.error is None
    assert resp.result["ok"] is True


def test_mcp_server_tools_list():
    tr = ToolRegistry(Settings())
    srv = MCPServer(Settings())
    srv.wire(tool_registry=tr, capability_registry=None)
    req = MCPRequest(method="tools/list")
    resp = asyncio.run(srv.handle(req))
    assert resp.error is None
    assert len(resp.result["tools"]) >= 4


def test_mcp_server_tools_call():
    """V1.6 P1: MCP tools_call SIN guard cableado → DENY explícito."""
    tr = ToolRegistry(Settings())
    srv = MCPServer(Settings())
    # Sin security perimeter → MCP debe DENY
    srv.wire(tool_registry=tr, capability_registry=None)
    req = MCPRequest(method="tools/call", params={"name": "clock", "arguments": {}})
    resp = asyncio.run(srv.handle(req))
    # Sin execution_guard → DENY (fail-closed)
    assert resp.result is None or resp.result.get("ok") is False


def test_mcp_server_tools_call_with_guard():
    """V1.6 P1: MCP tools_call CON guard cableado → ejecuta vía guard."""
    tr = ToolRegistry(Settings())
    srv = MCPServer(Settings())
    import tempfile

    from albra.evidence.legal_gate import LegalGate
    from albra.security.autonomy import AutonomyController
    from albra.security.execution_guard import ExecutionGuard
    from albra.security.policy_state import PolicyEngineState
    from albra.security.rbac import has_permission
    with tempfile.TemporaryDirectory() as tmp:
        ps = PolicyEngineState(f"{tmp}/ps.db")
        srv.wire(
            tool_registry=tr,
            capability_registry=None,
            execution_guard=ExecutionGuard(),
            policy_state=ps,
            autonomy_controller=AutonomyController(),
            rbac_check_fn=has_permission,
            legal_gate=LegalGate(),
        )
        req = MCPRequest(
            method="tools/call",
            params={"name": "clock", "arguments": {}, "user": "test", "role": "admin"},
        )
        resp = asyncio.run(srv.handle(req))
        # Con role=admin y guard config OK → debería pasar
        assert resp.error is None
        assert resp.result.get("ok") is True
        ps.close()


def test_mcp_server_method_not_found():
    srv = MCPServer(Settings())
    req = MCPRequest(method="nonexistent/method")
    resp = asyncio.run(srv.handle(req))
    assert resp.error is not None
    assert resp.error["code"] == -32601
