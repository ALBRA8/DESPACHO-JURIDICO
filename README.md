# DESPACHO JURÍDICO DIGITAL ALBRA

> **V2.5** — Agente jurídico colombiano con 12 módulos: Matters, Citation Audit, MCP server, White-label, X402 USDC billing, y más.

[![CI](https://github.com/ALBRA8/DESPACHO-JURIDICO/actions/workflows/ci.yml/badge.svg)](https://github.com/ALBRA8/DESPACHO-JURIDICO/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Version](https://img.shields.io/badge/version-2.5.1-green)
![Tests](https://img.shields.io/badge/tests-1072%20passed-brightgreen)

---

## Qué es ALBRA V2.5

ALBRA es un **agente jurídico colombiano** construido sobre metodología **ClonaKit clean-room**, inspirado en 27 referentes Legal OS (MikeOSS, GLAW, Lavern, Lawgent, Claude-Code-Law-Firm, Prism, QWED, CourtListener MCP, Moonlit, Claude for Legal, Harvey LAB, Awesome Legal Benchmarks, legal-rag-eval, CoCoBench, LawPortal, case.dev, Gotham, LawVu, NewMind, Agent Skills for Legal, y más).

### Stack
- **Backend**: Python 3.10+ · SQLite WAL · JSONL append-only · Markdown + YAML frontmatter · pytest
- **Frontend**: Next.js 16 · TypeScript 5 · Tailwind CSS 4 · shadcn/ui · Prisma 6
- **Corpus**: V1.2 (125 articles reales fetched con Playwright desde secretariasenado.gov.co)
- **Tests**: 1072 passed, 7 skipped
- **Lint**: ruff All checks passed

## 12 Módulos V2.0-V2.5

### V2.0 — Despacho Jurídico Base
| Módulo | Descripción |
|---|---|
| **Matters** | State machine monótono (8 estados, SQLite WAL, JSONL timeline) |
| **Agent Organigrama** | 5 agentes en markdown + YAML frontmatter (filing/intake/research/drafting/review) |
| **Citation Audit** | Pipeline extract→validate→retrace→reveal_or_block con fail-closed anti-hallucination |
| **Approval Chain** | Suggest→Prepare→Approve→Execute→Record con `minimum_human_signoff` |
| **Matter Audit** | JSONL hash chain SHA-256 tamper-evident por matter |

### V2.1 — Hardening Jurídico
| Módulo | Descripción |
|---|---|
| **DeadlineGuard** | 12 tipos de términos procesales colombianos (prescripción 20y/10y, tutela, demanda 15d, recursos 5d) |
| **ContradictionGuard** | Detecta contradicciones en cláusulas (regex accent-insensitive) |
| **AgenticCitator** | 8 treatment labels (followed/distinguished/doubted/overruled/per_incuriam/affirmed/reversed/cited) |

### V2.2 — Document Processing
| Módulo | Descripción |
|---|---|
| **Redline DOCX** | Tracked changes nativas (w:ins/w:del XML) + compare_docx_blackline |
| **RAG Local** | TF-IDF + cosine similarity (pure Python, no ML deps) |
| **Adversarial Pipeline** | RED→BLUE con MAGISTRADO ruling antes de file |
| **Playbooks** | 5 áreas (laboral/civil/constitucional/familia/corporativo) en markdown |

### V2.3 — Infrastructure + Corpus
| Módulo | Descripción |
|---|---|
| **Eval Suite** | Rubrics (essential/forbidden/bonus) + Legal Phantom Citation test (100% TPR/TNR) |
| **MCP Server** | 10 tools expuestas via stdio JSON-RPC 2.0 + HTTP transport con OAuth scaffold |
| **Citation Graph** | SQLite graph DB con 8 treatment labels |
| **IngestionCoordinator** | Fetch de fuentes colombianas oficiales + Playwright para JS-driven sites |
| **Corpus V1.2** | 125 articles reales (Constitución 32 + Ley 100 45 + Ley 80 48) via Playwright |
| **LLM Providers** | Scaffold modular: Mock (default), Anthropic, OpenAI, Ollama + LLMRouter con fallback |

### V2.4 — Enhancement
| Módulo | Descripción |
|---|---|
| **Scheduled Agents** | Event-driven triggers (matter_created, state_change, deadline_near, approval_pending) |
| **Memory Cell** | Cross-matter recall con TF-IDF (NewMind pattern) |
| **Precedent Board** | Promoción tentative→confirmed (Lavern pattern, 5 estados) |
| **Tabular Review** | Comparación N-documentos × M-cláusulas (9 tipos de cláusula) |

### V2.5 — Commercial
| Módulo | Descripción |
|---|---|
| **Skills Marketplace** | 15 skills pre-registradas (5 agents + 5 playbooks + 5 advanced tools) |
| **White-label** | Multi-tenant con branding + feature flags + license per tenant |
| **X402 Paid-Agent** | Service matrix + usage records + billing cycles (USDC settlement local) |
| **Install Log** | JSONL hash chain para skill installations (6 event types, 4 sources, 3 verdicts) |

## Corpus V1.2 — 125 articles reales

| Documento | Articles V1.1 | Articles V1.2 | Fuente |
|---|---|---|---|
| Constitución 1991 | 6 (arts 1,2,5,13,25,29) | **32** (arts 1-32) | secretariasenado.gov.co |
| Ley 100 de 1993 | 3 (arts 1,2,3) | **45** | secretariasenado.gov.co |
| Ley 80 de 1993 | 3 (arts 1,2,24) | **48** | secretariasenado.gov.co |
| **TOTAL** | **12** | **125 (10x)** | Playwright V2.3-E |

### Cadena de provenance

```
fuente oficial → Playwright fetch (HTML renderizado) → regex ARTICULO N.
    → cleanup (strip HTML tags + prefix 'o.') → article {number, text}
    → content_hash SHA-256 → real_corpus_v12.py → CitationAuditor(corpus_version='v12')
    → CitationGraph.add_node() → LocalRAG.index_document()
```

## CI

```yaml
jobs:
  lint:        # ruff check albra/ tests/
  test:        # pytest -v --tb=short en Python 3.10, 3.11, 3.12
  clean-room:  # git clone + checkout github.sha + pip install + lint + tests + CLI smoke
```

CI corre sobre el commit exacto (`github.sha`), no sobre `main` ambiguamente.

## Quick start

```bash
# Install
pip install -e ".[dev]"

# Set ephemeral secrets (fail-closed without these)
export ALBRA_JWT_SECRET="your-secret-here-32chars-min"
export ALBRA_ADMIN_PASSWORD="your-password-here-8chars-min"

# Run tests
pytest -v --tb=short

# Lint
ruff check albra/ tests/

# CLI
albra info
albra matter new --client "Juan Pérez" --area civil --parties "Pérez,Roa"
albra agent list
albra research "El artículo 1 de la Constitución Política de 1991..."
albra matter audit <matter-id>

# MCP server (stdio)
python -m albra.mcp.server

# MCP server (HTTP + OAuth scaffold)
python -m albra.mcp.server --http --port 8765 --no-auth
```

## Estructura del repositorio

```
albra/
├── matters/           V2.0: state machine + store + timeline
├── agents/             V2.0: 5 agentes markdown + YAML
├── knowledge/          V2.0: citation_audit + corpus V1.1/V1.2 + rag_local + citation_graph + ingestion_colombia
├── security/           V2.0: approval_chain + V2.1: deterministic_guard
├── audit/              V2.0: matter_audit + V2.5: install_log
├── documents/          V2.2: redline DOCX
├── reasoning/          V2.2: adversarial_pipeline + V2.4: precedent_board
├── review/             V2.4: tabular review
├── marketplace/        V2.5: skills + paid_agent_matrix
├── whitelabel/         V2.5: tenant manager
├── scheduling/         V2.4: scheduler
├── llm/                V2.3: providers (Mock/Anthropic/OpenAI/Ollama) + router
├── mcp/                V2.3: stdio + HTTP server (10 tools)
├── eval/               V2.3: rubrics + phantom citations
├── playbooks/          V2.2: 5 playbooks por área
└── ...                  V1.0-V1.6: 30 órganos del ADN ALBRA

tests/                   1072 tests covering all modules
.github/workflows/       CI: lint + test (3.10/3.11/3.12) + clean-room
CONTEXTO JURIDICO/       Estado actual + corpus + auditorías
docs/                    Arquitectura + auditorías V1-V2
```

## Licencia

Proprietary — ALBRA. Inspiración clean-room de 27 referentes Legal OS. Sin código copiado.
