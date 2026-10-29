# DESPACHO JURÍDICO — ESTADO ACTUAL

- **Estado del documento:** `V4.1 CIERRE DE SEGURIDAD RESIDUAL`
- **Última revisión documental:** 2026-10-29
- **Repositorio:** `ALBRA8/DESPACHO-JURIDICO`
- **HEAD inicial V4.1:** `d713c5c` (V4.0 CURRENT_STATE)
- **HEAD final V4.1:** `c5d5ae8` (V4.1 multitenant isolation end-to-end)
- **Push:** VERIFIED
- **CI:** Run `40813172756`, commit `c5d5ae8`, SUCCESS
  - lint: SUCCESS
  - test 3.10/3.11/3.12: 1271 passed, 5 skipped
  - clean-room: SUCCESS

## Commits V4.1

| SHA | Mensaje |
|---|---|
| `c5d5ae8` | multitenant isolation end-to-end (get_matter/advance_state/pending/approval/reject) |

## Bloqueo cerrado en V4.1

### Aislamiento multitenant end-to-end

**Antes (V4.0):** Solo `list_matters` filtraba por `tenant_id`. Las operaciones por ID
(`get_matter`, `advance_state`, `get_pending_action`, `list_pending`, `add_approval`,
`reject_action`) NO verificaban tenant → cross-tenant access por ID era posible.

**Ahora (V4.1):** TODAS las operaciones de `MatterStore` aceptan `tenant_id` y verifican
pertenencia antes de retornar o modificar datos.

| Operación | Verificación |
|---|---|
| get_matter(id, tenant_id) | WHERE id=? AND tenant_id=? → None si no match |
| advance_state(id, target, tenant_id) | get_matter with tenant → KeyError si no match |
| get_pending_action(id, tenant_id) | Verifica matter.tenant_id matches |
| list_pending(tenant_id) | JOIN matters WHERE tenant_id=? |
| add_approval(id, tenant_id) | get_pending_action with tenant → KeyError |
| reject_action(id, tenant_id) | get_pending_action with tenant → KeyError |

### Pruebas negativas (10 tests)

| Test | Demuestra |
|---|---|
| test_get_matter_tenant_a_cannot_read_tenant_b | Cross-tenant read by ID blocked |
| test_advance_state_tenant_a_cannot_advance_tenant_b | Cross-tenant advance blocked |
| test_list_pending_tenant_a_cannot_see_tenant_b | Cross-tenant pending enumeration blocked |
| test_get_pending_action_tenant_a_cannot_read_tenant_b | Cross-tenant pending read blocked |
| test_add_approval_tenant_a_cannot_approve_tenant_b | Cross-tenant approval blocked |
| test_reject_action_tenant_a_cannot_reject_tenant_b | Cross-tenant rejection blocked |
| test_mcp_list_matters_args_tenant_override_blocked | Args tenant_id override blocked |
| test_mcp_advance_matter_cross_tenant_blocked | MCP cross-tenant advance blocked |
| test_mcp_pending_isolated_by_tenant | Store-level isolation verified |
| test_legitimate_tenant_a_flows_work | No regression in legitimate flows |

## Arquitectura MCP V4.1

```
HTTP → Bearer → validate_bearer_token → AuthContext
  → call_tool(name, args, auth_context=ctx)
    → RBAC (check_tool_permission)
    → LegalGate (evaluate)
    → ExecutionGuard (check with policy_state, autonomy, rbac)
    → Prompt injection (is_prompt_injection) — fail-closed if unavailable
    → Inject _auth {tenant_id, role, identity, request_id} into args
    → Tool handler(args_with_auth)
      → _tool_list_matters: store.list_matters(tenant_id=args._auth.tenant_id)
      → _tool_advance_matter: store.advance_state(tenant_id=args._auth.tenant_id)
    → Audit (McpAuditEntry with input_hash, output_hash, correlation_id)
```

## Corpus por ruta

| Ruta | Corpus | Articles |
|---|---|---|
| MCP audit_citation | V1.3 | 125 |
| MCP search_corpus | V1.1 (default_rag) | 12 |

**Limitación:** search_corpus usa V1.1 porque LocalRAG.default_rag() carga V1.1.

## Limitaciones

| Componente | Estado |
|---|---|
| Corpus V1.3 raw_bytes | VERIFIED WITH LIMITATIONS |
| MCP OAuth production | BLOCKED BY EXTERNAL DEPENDENCY |
| LLM Anthropic/OpenAI | BLOCKED BY EXTERNAL DEPENDENCY |
| USDC settlement | BLOCKED BY EXTERNAL DEPENDENCY |
| Deployment | BLOCKED BY EXTERNAL DEPENDENCY |
| search_corpus V1.1 | VERIFIED WITH LIMITATIONS |
