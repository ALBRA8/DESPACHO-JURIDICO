# DESPACHO JURÍDICO — ESTADO ACTUAL

- **Estado del documento:** `UPDATED V2.5`
- **Última revisión documental:** 2026-10-28
- **Repositorio:** `ALBRA8/DESPACHO-JURIDICO`
- **Rama observada:** `main`
- **HEAD observado:** `81a9c83` (V2.3-H Corpus V1.2 + CitationAuditor configurable) — pendiente de push
- **HEAD remoto (GitHub):** `3191013` (V2.5-C+D — último push exitoso con PAT anterior)
- **Commits locales sin push:** 5 (V2.3-B+ MCP HTTP, V2.3-E Playwright, V2.3-F LLM, V2.3-G LLM integration, V2.3-H Corpus V1.2)
- **Estado de pruebas del HEAD local:** 1072 passed, 7 skipped (localmente verificado; NO verificado en CI remoto hasta push)
- **Estado de CI remoto:** `NOT VERIFIED` — el workflow YAML tenía bugs (branches `ain` sin `m`, docstring Python en YAML). Corregido localmente, pendiente de push.

## 1. Propósito del proyecto

Construir un agente jurídico colombiano digital con jurisdicción inicial en Colombia, separando arquitectura del agente, capacidades y conocimiento jurídico verificable.

## 2. Estado técnico observado (V2.5)

El HEAD local `81a9c83` contiene 12 módulos nuevos sobre el ARNÉS migration (`1bcf829`):

### V2.0 — Despacho Jurídico Base (commit `d88a63e`, pushed)
- Matters (state machine monótono 8 estados, SQLite WAL, JSONL timeline)
- Agent organigrama (5 agentes en markdown + YAML frontmatter)
- Citation audit (fail-closed anti-hallucination)
- Approval chain (`minimum_human_signoff`)
- Matter audit (JSONL hash chain SHA-256)

### V2.1 — Hardening Jurídico (commit `cc1e180`, pushed)
- DeadlineGuard (12 tipos de términos procesales colombianos)
- ContradictionGuard (regex accent-insensitive)
- AgenticCitator (8 treatment labels)

### V2.2 — Document Processing (commits `ac64ad4`→`9bc6b76`, pushed)
- Redline DOCX (tracked changes nativas w:ins/w:del)
- RAG local TF-IDF (pure Python, no ML deps)
- Adversarial RED→BLUE pipeline
- 5 playbooks (laboral/civil/constitucional/familia/corporativo)

### V2.3 — Infrastructure (commits `daee63c`→`81a9c83`, **5 commits pendientes de push**)
- Eval Suite (rubrics + Legal Phantom Citation test, 100% TPR/TNR local)
- MCP server (10 tools, stdio + HTTP transport + OAuth scaffold)
- Citation graph (SQLite con 8 treatment labels)
- IngestionCoordinator (Playwright para JS-driven sites)
- Corpus V1.2 (125 articles reales via Playwright)
- LLM providers scaffold (Mock/Anthropic/OpenAI/Ollama + router)
- LLMRouter integration en AdversarialPipeline

### V2.4 — Enhancement (commits `6c0c707`→`0301520`, pushed)
- Scheduled agents (event-driven triggers)
- Memory Cell (cross-matter recall, NewMind pattern)
- Precedent Board (tentative→confirmed, Lavern pattern)
- Tabular review (N×M clause comparison)

### V2.5 — Commercial (commits `324320b`→`3191013`, pushed)
- Skills marketplace (15 skills pre-registradas)
- White-label platform (multi-tenant)
- X402 paid-agent matrix (USDC settlement local)
- Install log (hash chain para skill installations)

## 3. Estado del conocimiento jurídico

### Corpus V1.1 (pushed, 12 articles)
- Constitución 1991: 6 articles (1, 2, 5, 13, 25, 29) — fetched de secretariasenado.gov.co
- Ley 100 de 1993: 3 articles (1, 2, 3) — fetched de secretariasenado.gov.co
- Ley 80 de 1993: 3 articles (1, 2, 24) — fetched de secretariasenado.gov.co
- **Verificación**: content_hash SHA-256 declarado, NO re-verificado contra fuente oficial en este momento.

### Corpus V1.2 (LOCAL_ONLY, 125 articles, commit `81a9c83`, pendiente de push)
- Constitución 1991: 32 articles (1-32) — fetched con Playwright V2.3-E
- Ley 100 de 1993: 45 articles — fetched con Playwright
- Ley 80 de 1993: 48 articles — fetched con Playwright
- **Verificación**: Playwright fetched exitosamente en runtime local. HTML size: 80,612 bytes (Constitución). Articles extraídos con regex `ARTICULO N.` + cleanup prefix `o.` (estilo legal colombiano `ARTICULO 1o.`).
- **Provenance chain**: source → Playwright fetch → regex extract → cleanup → article → content_hash → real_corpus_v12.py → CitationAuditor(corpus_version='v12')
- **Limitación**: NO verificado en CI remoto. `raw_content` es texto reconstruido (no el HTML crudo), pero content_hash es SHA-256 del texto reconstruido (no del HTML original). Esto es una limitación conocida: el hash garantiza integridad del texto almacenado, NO del HTML fuente.

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
- `CONTEXTO JURIDICO/ESTADO_CORPUS_JURIDICO.md` — estado del corpus

## 5. Bloqueos y cautelas

1. **Push pendiente**: 5 commits locales (V2.3-B+ through V2.3-H) sin push. Token GitHub (`(PAT redacted — ver GitHub settings)`) expirado/inválido (401). Requiere PAT nuevo.
2. **CI YAML corregido localmente**: branches `[main, develop]` (antes `ain`), docstring Python eliminado. Pendiente de push + verificación en GitHub Actions.
3. **Corpus V1.2 provenance**: chain documentada pero NO re-verificada contra fuente oficial en CI. El `raw_content` es texto reconstruido (limitación conocia, declarada arriba).
4. **LLM providers**: scaffold listo pero sin API key real. AnthropicProvider/OpenAIProvider retornan NotImplementedError V2.6. OllamaProvider hace HTTP real si Ollama está corriendo.
5. **MCP HTTP OAuth**: scaffold (accepts any non-empty bearer token). V2.6+: Auth0/Keycloak/GitHub OAuth App real.

## 6. Próximos pasos (bloqueados por accounts externos)

- Push 5 commits (requiere PAT nuevo)
- CI verification en GitHub Actions (requiere push)
- Deployment Vercel + Railway (requiere accounts)
- AWS Bogotá data residency (requiere AWS account)
- Real OAuth provider (requiere OAuth provider account)
- LLM real con Anthropic/OpenAI (requiere API key)
