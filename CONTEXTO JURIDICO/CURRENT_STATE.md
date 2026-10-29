# DESPACHO JURÍDICO — ESTADO ACTUAL

- **Estado del documento:** `V3.0 MEGA-OLEADAS COMPLETE`
- **Última revisión documental:** 2026-10-29
- **Repositorio:** `ALBRA8/DESPACHO-JURIDICO`
- **HEAD remoto:** `e9255f7` (feat: MEGA-OLEADA A+B — Security integration + deserialization fix + tenant isolation)
- **Push:** `VERIFIED` — todos los commits publicados
- **CI:** `VERIFIED` — Run `40796685936` terminó `SUCCESS`
  - lint: SUCCESS
  - test 3.10/3.11/3.12: 1253 passed, 5 skipped
  - clean-room: SUCCESS
- **Tests locales:** 1253 passed, 5 skipped
- **Lint:** ruff All checks passed

## 1. Arquitectura V3.0

12 módulos V2.0-V2.5 + hardening V2.6-V3.0:

### V2.0 — Despacho Jurídico Base
Matters (state machine monótono), Agent organigrama, Citation audit, Approval chain, Matter audit

### V2.1 — Hardening Jurídico
DeadlineGuard (12 tipos), ContradictionGuard, AgenticCitator (8 treatment labels)

### V2.2 — Document Processing
Redline DOCX (w:ins/w:del), RAG local TF-IDF, Adversarial RED→BLUE, 5 Playbooks

### V2.3 — Infrastructure
Eval Suite, MCP server (10 tools, stdio+HTTP+OAuth), Citation graph, IngestionCoordinator (Playwright), Corpus V1.3 (125 articles), LLM providers, LLMRouter integration

### V2.4 — Enhancement
Scheduled agents, Memory Cell, Precedent Board, Tabular review

### V2.5 — Commercial
Skills marketplace, White-label, X402 paid-agent, Install log

### V2.6-V3.0 — Hardening
Data boundaries (prompt injection), Ingestion pipeline (11 stages), Observability (CorrelationContext), LLM resilience (CircuitBreaker), CitationAuditor vigency, Playbook enforcement, Security audit (SSRF/path traversal/deserialization), ExecutionGuard wired to MCP, RBAC deny-by-default, Audit trail, AuthContext propagation (HTTP+stdio), pickle→JSON (deserialization fix), tenant_id isolation

## 2. MCP Security Chain (VERIFIED)

```
Request → Authentication → AuthContext → RBAC → LegalGate → ExecutionGuard →
  Prompt Injection Check → Tool Handler → Result → Audit
```

- HTTP: bearer → validate_bearer_token → AuthContext → call_tool(auth_context=ctx)
- stdio: initialize auth params → AuthContext → call_tool(auth_context=ctx)
- Production mode: fail-closed (returns None for all tokens without OAuth)
- Dev mode: auto-create dev context (backward compat)
- Test mode: role-prefixed tokens (test-abogado-xxx, test-socio-xxx)

## 3. Corpus (VERIFIED WITH LIMITATIONS)

- V1.3: 125 articles con provenance model de 4 niveles
- raw_bytes NOT STORED (HTML descartado por V1.2)
- Hash corresponde al texto reconstruido, NO al HTML fuente
- V1.4+ debe re-fetch preservando raw_bytes

## 4. Limitaciones

| Componente | Estado | Limitación |
|---|---|---|
| Corpus V1.3 | VERIFIED WITH LIMITATIONS | raw_bytes NOT STORED |
| MCP OAuth production | VERIFIED WITH LIMITATIONS | Requiere OAuth provider real |
| LLM Anthropic/OpenAI | VERIFIED WITH LIMITATIONS | Scaffold sin API key |
| LLM Ollama | VERIFIED WITH LIMITATIONS | HTTP real, fallback Mock sin Ollama |
| USDC settlement | BLOCKED BY EXTERNAL DEPENDENCY | Requiere Coinbase Commerce |
| Deployment | BLOCKED BY EXTERNAL DEPENDENCY | Requiere Vercel/Railway/AWS |
