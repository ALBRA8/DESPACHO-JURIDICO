# DESPACHO JURÍDICO — ESTADO ACTUAL

- **Estado del documento:** `VERIFIED V2.5`
- **Última revisión documental:** 2026-10-28
- **Repositorio:** `ALBRA8/DESPACHO-JURIDICO`
- **Rama observada:** `main`
- **HEAD remoto:** `392f416` (fix: CI test fix — playwright_available conditional)
- **Push:** `VERIFIED` — todos los commits están publicados en GitHub
- **CI:** `VERIFIED` — GitHub Actions run `40648009609` terminó `SUCCESS`
  - lint: SUCCESS
  - test 3.10: 1071 passed, 8 skipped
  - test 3.11: 1071 passed, 8 skipped
  - test 3.12: 1071 passed, 8 skipped
  - clean-room: SUCCESS (clone + checkout `392f416` + install + lint + tests + CLI smoke)

## 1. Propósito del proyecto

Construir un agente jurídico colombiano digital con jurisdicción inicial en Colombia, separando arquitectura del agente, capacidades y conocimiento jurídico verificable.

## 2. Estado técnico (V2.5, HEAD `392f416`)

### V2.0 — Despacho Jurídico Base (commit `d88a63e`)
- Matters (state machine monótono 8 estados, SQLite WAL, JSONL timeline)
- Agent organigrama (5 agentes en markdown + YAML frontmatter)
- Citation audit (fail-closed anti-hallucination)
- Approval chain (`minimum_human_signoff`)
- Matter audit (JSONL hash chain SHA-256)

### V2.1 — Hardening Jurídico (commit `cc1e180`)
- DeadlineGuard (12 tipos de términos procesales colombianos)
- ContradictionGuard (regex accent-insensitive)
- AgenticCitator (8 treatment labels)

### V2.2 — Document Processing (commits `ac64ad4`→`9bc6b76`)
- Redline DOCX (tracked changes nativas w:ins/w:del)
- RAG local TF-IDF (pure Python, no ML deps)
- Adversarial RED→BLUE pipeline
- 5 playbooks (laboral/civil/constitucional/familia/corporativo)

### V2.3 — Infrastructure (commits `daee63c`→`392f416`)
- Eval Suite (rubrics + Legal Phantom Citation test)
- MCP server (10 tools, stdio + HTTP transport + OAuth scaffold)
- Citation graph (SQLite con 8 treatment labels)
- IngestionCoordinator (Playwright para JS-driven sites)
- Corpus V1.2 (125 articles via Playwright)
- LLM providers scaffold (Mock/Anthropic/OpenAI/Ollama + router)
- LLMRouter integration en AdversarialPipeline

### V2.4 — Enhancement (commits `6c0c707`→`0301520`)
- Scheduled agents (event-driven triggers)
- Memory Cell (cross-matter recall, NewMind pattern)
- Precedent Board (tentative→confirmed, Lavern pattern)
- Tabular review (N×M clause comparison)

### V2.5 — Commercial (commits `324320b`→`3191013`)
- Skills marketplace (15 skills pre-registradas)
- White-label platform (multi-tenant)
- X402 paid-agent matrix (USDC settlement local)
- Install log (hash chain para skill installations)

## 3. Estado del conocimiento jurídico

### Corpus V1.1 (12 articles, published)
- Constitución 1991: 6 articles (1, 2, 5, 13, 25, 29)
- Ley 100 de 1993: 3 articles (1, 2, 3)
- Ley 80 de 1993: 3 articles (1, 2, 24)
- `content_hash` declarado pero `raw_content` es texto reconstruido, NO HTML crudo.

### Corpus V1.2 (125 articles, published, commit `81a9c83`)

**Estado: VERIFIED WITH LIMITATIONS**

- Constitución 1991: 32 articles (1-32)
- Ley 100 de 1993: 45 articles
- Ley 80 de 1993: 48 articles
- Playwright fetch verificado localmente (HTML 80,612 bytes Constitución).
- Tests pasan en CI (1071 passed, 8 skipped en 3.10/3.11/3.12).
- CitationAuditor(corpus_version='v12') indexa 125 articles.

**Limitación explícita (no oculta):**

`raw_content` es texto reconstruido (`"ARTICULO N. <text>"` concatenado), NO el HTML crudo capturado por Playwright de la fuente oficial. `content_hash` = SHA-256 del texto reconstruido, NO del HTML fuente.

Esto significa:
- ✓ Si alguien modifica un artículo en el código → el hash no coincide → detectable.
- ✗ NO garantiza que el texto almacenado coincide byte-a-byte con el HTML de la fuente.
- ✗ NO se conserva ni hashea el HTML crudo de origen.
- ✗ source→byte provenance = NOT VERIFIED.

Ver auditoría detallada en `CONTEXTO JURIDICO/PROVENANCE_V1_2.md`.

## 4. Documentación fuente

- `docs/ARCHITECTURE.md` — arquitectura V1.0
- `docs/CONSTRUCCION_V2.md` — arquitectura V2.0
- `docs/LEGAL_V2.md` — registro legal + checklist sala limpia
- `docs/CORPUS_PILOT_AUDIT_V1.md` — auditoría corpus V1.0 (FAIL)
- `docs/CORPUS_PILOT_AUDIT_V1_1.md` — auditoría corpus V1.1 (PASS)
- `docs/AUDIT_INDEPENDENT_V1.md` — auditoría V1.0
- `docs/AUDIT_INDEPENDENT_V2.md` — auditoría V1.6
- `docs/V1.6_INTEGRATION_COMPLETE.md` — reporte V1.6
- `docs/FINAL_REPORT.md` — reporte final V1.0
- `docs/PARITY_REPORT.md` — paridad holding V1.5
- `docs/IMPROVEMENTS.md` — mejoras exponenciales
- `CONTEXTO JURIDICO/CURRENT_STATE.md` — este documento
- `CONTEXTO JURIDICO/PROVENANCE_V1_2.md` — evidencia de provenance

## 5. Bloqueos y limitaciones declaradas

1. **Corpus V1.2 provenance**: `raw_content` es texto reconstruido. No se conserva HTML crudo ni su hash. source→byte provenance = NOT VERIFIED.
2. **LLM providers**: Mock VERIFIED. Anthropic/OpenAI = scaffold sin API key real (NotImplementedError V2.6). Ollama = HTTP real pero CI sin Ollama running.
3. **MCP HTTP OAuth**: scaffold acepta any non-empty bearer token. No es seguro para producción.
4. **MCP HTTP RBAC/ExecutionGuard**: NOT VERIFIED. El server no integra RBAC ni ExecutionGuard.
5. **MCP HTTP audit trail**: NOT VERIFIED. El server no escribe al audit log en tool calls.
6. **MCP HTTP runtime smoke**: LOCAL_ONLY. Tests pasan en CI pero el runtime (curl /mcp/health, /mcp/tools/call) solo verificado localmente.
