# DESPACHO JURÍDICO — ESTADO ACTUAL

- **Estado del documento:** `V4.0 CIERRE INTEGRAL`
- **Última revisión documental:** 2026-10-29
- **Repositorio:** `ALBRA8/DESPACHO-JURIDICO`
- **HEAD inicial:** `bead239` (V3.0 MEGA-OLEADAS)
- **HEAD final:** `e5afb88` (V4.0 — 8 tests que prueban los 3 fixes críticos)
- **Push:** VERIFIED
- **CI:** Run `40810071960`, commit `e5afb88`, SUCCESS
  - lint: SUCCESS
  - test 3.10/3.11/3.12: 1261 passed, 5 skipped
  - clean-room: SUCCESS

## Commits V4.0

| SHA | Mensaje |
|---|---|
| `7d8bc4a` | prompt injection fail-closed + corpus V1.3 + tenant isolation in list_matters |
| `e5afb88` | 8 tests que prueban los 3 fixes críticos con evidencia real |

## Bloqueos cerrados en V4.0

### 1. Prompt injection fail-closed
**Antes:** `except ImportError: pass` → continuaba sin protección si data_boundary no cargaba.
**Ahora:** DENY con audit entry si detector no disponible.
**Tests:** 3 (injection detected → DENY, ImportError → DENY, clean text → executes)

### 2. Corpus V1.3 en MCP audit_citation
**Antes:** `CitationAuditor()` usaba V1.1 (12 articles).
**Ahora:** `CitationAuditor(corpus_version="v13")` usa V1.3 (125 articles).
**Tests:** 2 (art 3 V1.3-only → revealed, V1.3 ≥125 vs V1.1=12)

### 3. Tenant isolation en list_matters
**Antes:** list_matters no filtraba por tenant_id → cross-tenant data leak.
**Ahora:** tenant_id derivado de auth_context (no del cliente), pasado a store.list_matters.
**Tests:** 3 (tenant-A sees A not B, args override blocked, cross-tenant matter blocked)

## Arquitectura de ejecución MCP (V4.0)

```
HTTP Request → Bearer extraction → validate_bearer_token(mode) → AuthContext
    → call_tool(name, args, auth_context=ctx)
        → if production and no ctx → DENY (fail-closed)
        → RBAC: check_tool_permission(name, ctx)
        → LegalGate: evaluate("tool_invocation")
        → ExecutionGuard: check(policy_state, autonomy, rbac, legal_verdict)
        → Prompt injection: is_prompt_injection(str(args)) → DENY if detected
        → if ImportError → DENY (fail-closed)
        → Inject _auth metadata (tenant_id, role, identity, request_id) into args
        → Tool handler(args_with_auth)
        → Audit: McpAuditEntry (input_hash, output_hash, correlation_id)
```

## Corpus por ruta

| Ruta | Corpus | Articles |
|---|---|---|
| MCP audit_citation | V1.3 | 125 |
| MCP search_corpus | V1.1 (via default_rag) | 12 |
| CitationAuditor(corpus_version="v11") | V1.1 | 12 |
| CitationAuditor(corpus_version="v12") | V1.2 | 125 |
| CitationAuditor(corpus_version="v13") | V1.3 | 125 + provenance |

**Limitación:** search_corpus usa V1.1 porque LocalRAG.default_rag() carga V1.1.
V1.4+ debe actualizar default_rag() para usar V1.3.

## Persistencia

| Componente | Sobrevive reinicio? | Mecanismo |
|---|---|---|
| MatterStore | SÍ | SQLite WAL (data/matters.db) |
| MatterAudit | SÍ | JSONL append-only |
| McpAuditLog | SÍ | JSONL append-only |
| InstallLog | SÍ | JSONL hash chain |
| LocalRAG | SÍ | JSON persist (data/rag_index.json) |
| MemoryCell | SÍ | SQLite (data/memory_cell.db) |
| CitationGraph | SÍ | SQLite (data/citation_graph.db) |
| PrecedentBoard | SÍ | SQLite (data/precedent_board.db) |

## Limitaciones

| Componente | Estado | Causa |
|---|---|---|
| Corpus V1.3 raw_bytes | VERIFIED WITH LIMITATIONS | HTML descartado por V1.2 |
| MCP OAuth production | BLOCKED BY EXTERNAL DEPENDENCY | Requiere OAuth provider |
| LLM Anthropic/OpenAI | BLOCKED BY EXTERNAL DEPENDENCY | Requiere API key |
| USDC settlement | BLOCKED BY EXTERNAL DEPENDENCY | Requiere Coinbase Commerce |
| Deployment | BLOCKED BY EXTERNAL DEPENDENCY | Requiere Vercel/Railway/AWS |
| search_corpus usa V1.1 | VERIFIED WITH LIMITATIONS | default_rag() carga V1.1 |
