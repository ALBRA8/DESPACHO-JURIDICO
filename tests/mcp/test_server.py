"""Tests del MCP server público V2.3-B.

Cobertura (20 tests):
- Singleton get_mcp_server
- register_tool / list_tools
- 10 tools default: audit_citation, search_corpus, verify_deadline,
  analyze_treatment, advance_matter, verify_audit_chain, list_matters,
  list_agents, get_playbook, run_eval_suite
- call_tool: dict return, error on unknown, error on missing arg,
  error on handler exception
- JSON-RPC 2.0 dispatch: initialize, tools/list, tools/call format,
  method not found, shutdown, parse error path
"""
from __future__ import annotations

import json

import pytest

from albra.mcp.server import McpServer, get_mcp_server

# ===== Fixtures =====

@pytest.fixture
def strong_secrets(monkeypatch):
    monkeypatch.setenv("ALBRA_JWT_SECRET", "test-ephemeral-jwt-secret-32-chars")
    monkeypatch.setenv("ALBRA_ADMIN_PASSWORD", "test-ephemeral-pass-1234")


@pytest.fixture
def store(strong_secrets, tmp_path):
    from albra.matters.store import MatterStore
    s = MatterStore(str(tmp_path / "matters.db"))
    yield s
    s.close()


@pytest.fixture
def audit(strong_secrets, tmp_path):
    from albra.audit.matter_audit import MatterAudit
    return MatterAudit(str(tmp_path / "matters"))


@pytest.fixture
def server(strong_secrets, store, audit):
    return McpServer(matter_store=store, matter_audit=audit)


@pytest.fixture
def fresh_server(strong_secrets):
    """Server sin inyección de store (usa defaults; sólo para tests que no
    tocan matters)."""
    return McpServer()


# ===== Singleton =====

def test_server_singleton(strong_secrets, monkeypatch):
    """get_mcp_server() devuelve la misma instancia en llamadas sucesivas."""
    import albra.mcp.server as mod
    # Reset singleton antes del test
    monkeypatch.setattr(mod, "_server", None)
    s1 = mod.get_mcp_server()
    s2 = mod.get_mcp_server()
    assert s1 is s2
    assert isinstance(s1, McpServer)
    # Limpieza para no afectar a otros tests
    monkeypatch.setattr(mod, "_server", None)


# ===== register_tool / list_tools =====

def test_register_tool_adds_custom_tool(server):
    """register_tool añade una tool accesible vía list_tools y call_tool."""
    def echo_handler(args: dict) -> dict:
        return {"echo": args.get("msg", "")}

    server.register_tool(
        "custom_echo",
        "Echo tool for testing",
        {
            "type": "object",
            "properties": {"msg": {"type": "string"}},
            "required": ["msg"],
        },
        echo_handler,
    )
    names = [t["name"] for t in server.list_tools()]
    assert "custom_echo" in names
    # call_tool funciona
    result = server.call_tool("custom_echo", {"msg": "hello"})
    assert result == {"echo": "hello"}


def test_list_tools_returns_all_10(server):
    """Por defecto el McpServer registra las 10 tools ALBRA."""
    tools = server.list_tools()
    assert len(tools) == 10
    expected_names = {
        "audit_citation", "search_corpus", "verify_deadline",
        "analyze_treatment", "advance_matter", "verify_audit_chain",
        "list_matters", "list_agents", "get_playbook", "run_eval_suite",
    }
    actual_names = {t["name"] for t in tools}
    assert actual_names == expected_names
    # Cada tool tiene los 3 campos MCP
    for t in tools:
        assert "description" in t
        assert "inputSchema" in t
        assert isinstance(t["inputSchema"], dict)
        assert t["inputSchema"].get("type") == "object"


# ===== call_tool: success cases =====

def test_call_tool_audit_citation_returns_dict(server):
    """audit_citation con Constitución 1991 art 13 → revealed=True, verified."""
    text = "El artículo 13 de la Constitución Política de 1991 garantiza la igualdad."
    result = server.call_tool("audit_citation", {"text": text})
    assert isinstance(result, dict)
    assert result["revealed"] is True
    assert result["verified_count"] >= 1
    assert result["unverified_count"] == 0
    assert result["rejected_count"] == 0
    assert "Constitución Política de 1991" in str(result["verified"])


def test_call_tool_search_corpus_returns_list(server):
    """search_corpus con query de salud → list[chunk] no vacío."""
    result = server.call_tool("search_corpus", {"query": "salud artículo 13", "k": 3})
    assert isinstance(result, dict)
    assert "results" in result
    assert isinstance(result["results"], list)
    assert "count" in result
    # Corpus tiene 12 chunks; artículo 13 debería aparecer
    assert result["count"] >= 1
    assert result["count"] <= 3
    first = result["results"][0]
    assert "document_name" in first
    assert "text" in first
    assert "score" in first


def test_call_tool_verify_deadline_valid_type(server):
    """verify_deadline con tipo válido y dentro del plazo → ok=True."""
    result = server.call_tool("verify_deadline", {
        "claim_date": "2020-01-01",
        "event_date": "2025-01-01",
        "deadline_type": "prescripcion_civil_extracontractual",
    })
    assert result.get("ok") is True
    assert result.get("expired") is False
    assert "days_elapsed" in result
    assert "deadline_days" in result
    assert "remaining_days" in result
    assert "reason" in result


def test_call_tool_verify_deadline_invalid_type_returns_error(server):
    """verify_deadline con tipo inválido → error dict (ValueError capturado)."""
    result = server.call_tool("verify_deadline", {
        "claim_date": "2020-01-01",
        "event_date": "2025-01-01",
        "deadline_type": "nonexistent_type_xyz",
    })
    assert "error" in result
    assert "nonexistent_type_xyz" in result["error"] or "Unknown" in result["error"]


def test_call_tool_analyze_treatment_returns_treatment(server):
    """analyze_treatment con texto 'aplicando' → treatment='followed'."""
    text = (
        "El juez aplicando el mismo criterio de la sentencia C-251/2002 "
        "resolvió el caso concreto."
    )
    result = server.call_tool("analyze_treatment", {
        "citing_text": text,
        "cited_decision_id": "C-251/2002",
    })
    assert result["treatment"] == "followed"
    assert result["confidence"] >= 0.5
    assert result["cited_decision_id"] == "C-251/2002"
    assert "evidence" in result
    assert "reason" in result


def test_call_tool_list_matters_empty(server):
    """list_matters en store vacío → matters=[], count=0."""
    result = server.call_tool("list_matters", {})
    assert result == {"matters": [], "count": 0}


def test_call_tool_list_agents_returns_5(server):
    """list_agents → organigrama con 5 agentes."""
    result = server.call_tool("list_agents", {})
    assert result["count"] == 5
    assert len(result["agents"]) == 5
    ids = [a["id"] for a in result["agents"]]
    assert "filing-agent" in ids
    assert "intake-agent" in ids


def test_call_tool_get_playbook_laboral(server):
    """get_playbook('laboral') → Playbook.as_dict() con practice_area='laboral'."""
    result = server.call_tool("get_playbook", {"practice_area": "laboral"})
    assert result["practice_area"] == "laboral"
    assert "workflow_states" in result
    assert "deadline_types" in result
    assert "citation_corpus" in result
    assert "red_flags" in result
    # Sanity: laboral playbook mentions Constitución 1991
    assert "Constitución Política de 1991" in result["citation_corpus"]


def test_call_tool_get_playbook_unknown_returns_error(server):
    """get_playbook('nonexistent') → error dict (ValueError capturado)."""
    result = server.call_tool("get_playbook", {"practice_area": "nonexistent_area"})
    assert "error" in result
    assert "nonexistent_area" in result["error"]


def test_call_tool_run_eval_suite_returns_summary(server):
    """run_eval_suite() → dict con summary.all_passed=True (V2.3-A pasa 100%)."""
    result = server.call_tool("run_eval_suite", {})
    assert isinstance(result, dict)
    assert "rubrics" in result
    assert "phantom" in result
    assert "summary" in result
    summary = result["summary"]
    assert summary["rubrics_total"] == 3
    assert summary["rubrics_passed"] == 3
    assert summary["phantom_tpr"] == 1.0
    assert summary["phantom_tnr"] == 1.0
    assert summary["all_passed"] is True


# ===== call_tool: error cases =====

def test_call_unknown_tool_returns_error(server):
    """call_tool con name no registrado → {'error': 'Unknown tool: ...'}."""
    result = server.call_tool("does_not_exist", {})
    assert "error" in result
    assert "Unknown tool" in result["error"]
    assert "does_not_exist" in result["error"]


def test_call_tool_with_missing_required_arg_returns_error(server):
    """call_tool('audit_citation', {}) sin 'text' → error dict (KeyError capturado)."""
    result = server.call_tool("audit_citation", {})
    assert "error" in result
    assert "text" in result["error"]


def test_call_tool_handler_exception_returns_error_dict(server):
    """Si una tool handler levanta excepción → error dict con el mensaje."""
    def boom_handler(args: dict) -> dict:
        raise RuntimeError("kaboom!")

    server.register_tool(
        "boom",
        "Tool that always raises",
        {"type": "object", "properties": {}, "required": []},
        boom_handler,
    )
    result = server.call_tool("boom", {})
    assert "error" in result
    assert "kaboom" in result["error"]


# ===== JSON-RPC 2.0 dispatch =====

def test_initialize_method_returns_server_info(server):
    """handle_request(initialize) → result.serverInfo.name == 'ALBRA-MCP'."""
    response = server.handle_request({
        "jsonrpc": "2.0",
        "id": "req-1",
        "method": "initialize",
        "params": {},
    })
    assert "result" in response
    assert "error" not in response
    result = response["result"]
    assert result["serverInfo"]["name"] == "ALBRA-MCP"
    assert result["serverInfo"]["version"]


def test_json_rpc_initialize_format(server):
    """initialize response cumple formato JSON-RPC 2.0 + campos MCP."""
    response = server.handle_request({
        "jsonrpc": "2.0",
        "id": "rpc-init",
        "method": "initialize",
        "params": {},
    })
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == "rpc-init"
    assert "result" in response
    result = response["result"]
    assert result["protocolVersion"] == "2024-11-05"
    assert "serverInfo" in result
    assert "capabilities" in result
    assert "tools" in result["capabilities"]
    assert result["capabilities"]["tools"]["listChanged"] is True


def test_json_rpc_tools_list_format(server):
    """tools/list response → result.tools es lista de 10 dicts con name/description/inputSchema."""
    response = server.handle_request({
        "jsonrpc": "2.0",
        "id": "rpc-list",
        "method": "tools/list",
        "params": {},
    })
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == "rpc-list"
    assert "result" in response
    tools = response["result"]["tools"]
    assert len(tools) == 10
    for t in tools:
        assert "name" in t
        assert "description" in t
        assert "inputSchema" in t
        assert isinstance(t["inputSchema"], dict)


def test_json_rpc_tools_call_format(server):
    """tools/call response → result.content[0].text es JSON serializable con la tool result."""
    response = server.handle_request({
        "jsonrpc": "2.0",
        "id": "rpc-call",
        "method": "tools/call",
        "params": {
            "name": "audit_citation",
            "arguments": {
                "text": "El artículo 13 de la Constitución Política de 1991 garantiza la igualdad.",
            },
        },
    })
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == "rpc-call"
    assert "result" in response
    result = response["result"]
    assert "content" in result
    assert len(result["content"]) == 1
    content = result["content"][0]
    assert content["type"] == "text"
    # El texto es JSON serializado del resultado de audit_citation
    inner = json.loads(content["text"])
    assert inner["revealed"] is True
    assert inner["verified_count"] >= 1
    assert result["isError"] is False


def test_json_rpc_tools_call_unknown_tool_iserror(server):
    """tools/call con tool desconocida → isError=True, content contiene el error."""
    response = server.handle_request({
        "jsonrpc": "2.0",
        "id": "rpc-unknown",
        "method": "tools/call",
        "params": {
            "name": "nonexistent_tool",
            "arguments": {},
        },
    })
    assert response["jsonrpc"] == "2.0"
    result = response["result"]
    assert result["isError"] is True
    inner = json.loads(result["content"][0]["text"])
    assert "error" in inner
    assert "nonexistent_tool" in inner["error"]


def test_json_rpc_method_not_found(server):
    """Método JSON-RPC desconocido → error code -32601 (Method not found)."""
    response = server.handle_request({
        "jsonrpc": "2.0",
        "id": "rpc-bad",
        "method": "nonexistent/method",
        "params": {},
    })
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == "rpc-bad"
    assert "error" in response
    assert response["error"]["code"] == -32601
    assert "Method not found" in response["error"]["message"]


def test_json_rpc_shutdown(server):
    """shutdown method → result.shutdown=True."""
    response = server.handle_request({
        "jsonrpc": "2.0",
        "id": "rpc-shutdown",
        "method": "shutdown",
        "params": {},
    })
    assert response["jsonrpc"] == "2.0"
    assert response["result"]["shutdown"] is True
    assert response["result"]["ok"] is True


def test_json_rpc_ping(server):
    """ping method → result.ok=True (MCP heartbeat)."""
    response = server.handle_request({
        "jsonrpc": "2.0",
        "id": "rpc-ping",
        "method": "ping",
        "params": {},
    })
    assert response["result"]["ok"] is True


def test_json_rpc_notification_no_response(server):
    """Requests sin 'id' son notifications → handle_request devuelve {} (no response)."""
    response = server.handle_request({
        "jsonrpc": "2.0",
        "method": "tools/list",
        "params": {},
    })
    assert response == {}


def test_json_rpc_invalid_params_for_tools_call(server):
    """tools/call sin 'name' en params → error code -32602 (Invalid params)."""
    response = server.handle_request({
        "jsonrpc": "2.0",
        "id": "rpc-no-name",
        "method": "tools/call",
        "params": {"arguments": {}},  # sin 'name'
    })
    assert response["error"]["code"] == -32602
    assert "name" in response["error"]["message"]
