# DESPACHO JURÍDICO — ESTADO ACTUAL

- **Estado del documento:** `V5.0 HARDENING INTEGRAL`
- **Última revisión documental:** 2026-10-29
- **Repositorio:** `ALBRA8/DESPACHO-JURIDICO`
- **HEAD inicial V5.0:** `cdbd795` (V4.1 CURRENT_STATE)
- **HEAD final V5.0:** `d10f40f` (V5.0 verify_audit_chain tenant isolation)
- **Push:** VERIFIED
- **CI:** Run `40814871546`, commit `d10f40f`, SUCCESS
  - lint: SUCCESS
  - test 3.10/3.11/3.12: 1275 passed, 5 skipped
  - clean-room: SUCCESS

## Commits V5.0

| SHA | Mensaje |
|---|---|
| `d10f40f` | verify_audit_chain tenant isolation + list_matters consistency + CLI documented |

## Bloqueos cerrados en V5.0

### 1. verify_audit_chain cross-tenant access
**Antes:** `_tool_verify_audit_chain` no verificaba tenant_id → tenant-A podía leer audit chain de tenant-B.
**Ahora:** Verifica `store.get_matter(matter_id, tenant_id=tenant_id)` antes de leer audit.

### 2. list_matters get_matter consistency
**Antes:** `list_matters` filtraba por tenant en SQL pero `get_matter(mid)` no pasaba tenant.
**Ahora:** `get_matter(mid, tenant_id=tenant_id)` — re-verificación consistente.

### 3. CLI documented as LOCAL_ONLY
**Limitación documentada:** CLI commands llaman MatterStore directamente sin AuthContext.
Aceptable para desarrollo local. Producción usa MCP HTTP que enforcea tenant_id.

### 4. All MatterStore methods verified
Test automatizado verifica que get_matter, advance_state, get_pending_action,
list_pending, add_approval, reject_action, list_matters — todos aceptan tenant_id.

## Arquitectura de seguridad MCP V5.0

```
HTTP → Bearer → validate_bearer_token(mode) → AuthContext
  → call_tool(name, args, auth_context=ctx)
    → [production mode + no ctx → DENY fail-closed]
    → RBAC: check_tool_permission(name, ctx)
    → LegalGate: evaluate("tool_invocation")
    → ExecutionGuard: check(policy_state, autonomy, rbac_fn, legal_verdict)
    → Prompt injection: is_prompt_injection(str(args)) [fail-closed if unavailable]
    → Inject _auth {tenant_id, role, identity, request_id} into args
    → Tool handler(args_with_auth):
        _tool_list_matters:     store.list_matters(tenant_id=args._auth.tenant_id)
        _tool_advance_matter:    store.advance_state(tenant_id=args._auth.tenant_id)
        _tool_verify_audit_chain: store.get_matter(tenant_id=args._auth.tenant_id) → verify
    → Audit: McpAuditEntry (input_hash, output_hash, correlation_id)
```

## Rutas de ejecución y su estado de aislamiento

| Ruta | tenant_id enforced? | Estado |
|---|---|---|
| MCP HTTP tools/call | SÍ (auth_context.tenant_id → _auth → store) | VERIFIED |
| MCP stdio tools/call | SÍ (initialize auth → _stdio_auth_context → _auth → store) | VERIFIED |
| MCP HTTP list_matters | SÍ | VERIFIED |
| MCP HTTP advance_matter | SÍ | VERIFIED |
| MCP HTTP verify_audit_chain | SÍ (V5.0 fix) | VERIFIED |
| CLI matter_show | NO (local development only) | LOCAL_ONLY |
| CLI matter_advance | NO (local development only) | LOCAL_ONLY |
| CLI matter_list | NO (local development only) | LOCAL_ONLY |
| MCPServer._m_tools_call (V1.6) | NO (legacy, not reachable from V2.3+ McpServer) | NOT_REACHABLE |

## Corpus por ruta

| Ruta | Corpus | Articles |
|---|---|---|
| MCP audit_citation | V1.3 | 125 |
| MCP search_corpus | V1.1 (default_rag) | 12 |

## Limitaciones

| Componente | Estado |
|---|---|
| Corpus V1.3 raw_bytes | VERIFIED WITH LIMITATIONS |
| search_corpus V1.1 | VERIFIED WITH LIMITATIONS |
| CLI sin tenant_id | LOCAL_ONLY (documented) |
| MCPServer._m_tools_call | NOT_REACHABLE (legacy) |
| MCP OAuth production | BLOCKED BY EXTERNAL DEPENDENCY |
| LLM Anthropic/OpenAI | BLOCKED BY EXTERNAL DEPENDENCY |
| USDC settlement | BLOCKED BY EXTERNAL DEPENDENCY |
| Deployment | BLOCKED BY EXTERNAL DEPENDENCY |
