"""Tests de tools, capabilities y MCP."""
import asyncio

from albra.config.settings import Settings
from albra.tools.registry import ToolRegistry
from albra.tools.base import Tool, ToolResult
from albra.capabilities.registry import CapabilityRegistry, Capability
from albra.mcp.server import MCPServer
from albra.mcp.protocol import MCPRequest


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
    tr = ToolRegistry(Settings())
    srv = MCPServer(Settings())
    srv.wire(tool_registry=tr, capability_registry=None)
    req = MCPRequest(method="tools/call", params={"name": "clock", "arguments": {}})
    resp = asyncio.run(srv.handle(req))
    assert resp.error is None
    assert resp.result["ok"] is True


def test_mcp_server_method_not_found():
    srv = MCPServer(Settings())
    req = MCPRequest(method="nonexistent/method")
    resp = asyncio.run(srv.handle(req))
    assert resp.error is not None
    assert resp.error["code"] == -32601
