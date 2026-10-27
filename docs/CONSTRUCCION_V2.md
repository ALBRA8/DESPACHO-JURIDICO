# CONSTRUCCIÓN — Despacho Jurídico Digital ALBRA V2.0

> Documento de arquitectura para desarrolladores. NO se publica como
> user-facing. Vive en `docs/` y guía la comprensión del código.

## Resumen

ALBRA V2.0 añade al agente existente (V1.0-V1.6 + ARNÉS migration)
**5 funciones nuevas** centradas en el workflow de un despacho jurídico
colombiano. Se construyó siguiendo la metodología ClonaKit (clean-room):
la FICHA es el único input del constructor; los informes de investigación
de los 15 referentes NO son visibles para el código.

## Arquitectura V2.0

```
albra/
├── matters/                ← NUEVO V2.0
│   ├── matter.py           (state machine monótono: 8 estados, 8 transiciones)
│   ├── store.py            (SQLite WAL: matters + parties + pending_actions)
│   └── timeline.py         (JSONL append-only por matter)
├── agents/                 ← NUEVO V2.0
│   ├── loader.py           (parser markdown + YAML frontmatter)
│   └── definitions/        (5 agentes: intake/research/drafting/review/filing)
├── knowledge/
│   └── citation_audit.py   ← NUEVO V2.0 (pipeline extract→validate→retrace→reveal_or_block)
├── security/
│   └── approval_chain.py   ← NUEVO V2.0 (Suggest→Prepare→Approve→Execute→Record)
├── audit/
│   └── matter_audit.py     ← NUEVO V2.0 (JSONL hash chain por matter)
├── config/
│   └── settings.py         (extendido: matter_db_path, matter_data_dir)
└── cli.py                  (extendido: grupos matter/agent/pending + research)
```

## 5 Funciones del MVP

### 1. Matters como unidad central

**Patrón**: state machine monótono, 8 estados, 8 transiciones permitidas.

```
NUEVO → INTAKE → PLANEACIÓN → EJECUTANDO → BORRADOR-FINAL →
EN-ESPERA-DE-APROBACIÓN → LISTO-PARA-CLIENTE → FIRMADO-Y-ENTREGADO
                                                    (terminal)
```

Única retrocesión permitida: `EN-ESPERA-DE-APROBACIÓN → BORRADOR-FINAL`
(rechazo de aprobación → loop de retrabajo explícito).

**Archivos clave**:
- `albra/matters/matter.py` — `Matter` dataclass + `MatterState` constants
- `albra/matters/store.py` — `MatterStore` (SQLite WAL, schema: matters/parties/pending_actions)
- `albra/matters/timeline.py` — `MatterTimeline` (JSONL append-only)

### 2. Agent/skill organigrama en markdown

**Patrón**: cada agente es un archivo `.md` con YAML frontmatter.

5 agentes definidos (organigrama 3-tier):

| ID | Tier | Reports To | Min Signoff |
|---|---|---|---|
| filing-agent | leadership | nobody | 1 |
| intake-agent | specialist | filing-agent | 0 |
| research-agent | specialist | filing-agent | 0 |
| drafting-agent | specialist | filing-agent | 0 |
| review-agent | specialist | filing-agent | 0 |

**Campos obligatorios en frontmatter**: id, name, tier, reports_to,
escalates_to, delegates_to, tools, minimum_human_signoff, practice_areas.

**Parser**: `albra/agents/loader.py` — sin dependencia YAML externa, parser
manual que soporta strings, ints, lists multiline y lists inline `[]`.

### 3. Citation audit pre-reveal con fail-closed

**Pipeline**: extract_citations → validate_against_corpus → retrace_quotes → reveal_or_block.

**Patrones de cita detectados**:
- `artículo N de la Constitución [Política de 1991]`
- `Ley N de YYYY[, artículo M]`
- `Sentencia X-NN/YYYY` (con prefijo "Sentencia" o "Sentencias")
- Standalone: `X-NN/YYYY` (sin prefijo) para C, T, SU, SL, MP, A y años 1990-2030
- Quote: texto entre comillas de ≥10 chars asociado a la cita más cercana (≤200 chars de distancia)

**Corpus válido** (V1.1 existente):
- Constitución 1991, artículos 1, 2, 5, 13, 25, 29
- Ley 100 de 1993, artículos 1, 2, 3
- Ley 80 de 1993, artículos 1, 2, 24

**Documentos rechazados** (lookup rápido): Ley 1480, Sentencia C-251/2002,
Sentencia T-760/2008, Sentencia AR-001/2020, Doctrina Temis.

### 4. Approval chain con minimum_human_signoff

**Cadena**: Suggest → Prepare → Approve → Execute → Record.

**Defaults por action_type**:
- `publish_legal_filing`: 1 firma (abogado+)
- `sign_document`: 1 firma (abogado+)
- `send_external_message`: 1 firma (abogado+)
- `accept_contract`: 2 firmas (abogado + cliente, roles distintos)
- `modify_permissions`: 2 firmas (socio + abogado)
- `financial_action`: 2 firmas (socio + abogado)

**Roles jerárquicos**: paralegal(1) < abogado(2) < socio(3) < cliente(4).
Solo roles técnicos (abogado/socio) pueden firmar acciones técnicas.

### 5. Audit log JSONL matter-scoped con hash chain

**Formato**: `data/matters/<matter_id>/audit.jsonl` (una línea JSON por acción).

**Campos por entry**: ts, actor, authority, model, action_type, action_payload,
result, prev_hash, this_hash.

**Hash chain**: SHA-256 de (entry sin this_hash + prev_hash).
- Genesis prev_hash: `"0" * 64`
- Modificar un entry rompe la cadena → `verify_chain()` detecta.

## CLI V2.0

```
albra matter new/list/show/advance/timeline/audit
albra agent list/show/reload
albra pending list, albra pending approve <id> --by --role --comment
albra research "<texto>" [--matter <id>]
```

## Tests V2.0

- `tests/matters/test_matter_state.py` — 10 tests state machine
- `tests/matters/test_store.py` — 17 tests SQLite WAL + pending_actions
- `tests/matters/test_timeline.py` — 7 tests JSONL timeline
- `tests/agents/test_loader.py` — 23 tests markdown+YAML parser
- `tests/knowledge/test_citation_audit.py` — 25 tests citation audit pipeline
- `tests/security/test_approval_chain.py` — 27 tests approval chain
- `tests/audit/test_matter_audit.py` — 17 tests matter-scoped audit log

Total V2.0: +127 tests (de 491 a 618 passed).

## Stack

- Python 3.10+
- SQLite WAL (matters, parties, pending_actions)
- JSONL append-only (timeline, audit)
- Markdown + YAML frontmatter (agent definitions)
- pytest (618 passed, 5 skipped)
- ruff lint (All checks passed)

## Inspiración (clean-room)

Construido a partir de la FICHA V2.0 (que sintetizó patrones de 15
referentes Legal OS en informe clean-room). NO se copió código de los
referentes originales. Patrones recreados desde cero sobre el stack
Python del proyecto ALBRA.

Referentes investigados (informe separado en
`/home/z/my-project/despacho-evolution/clones/despacho-juridico-v2/investigacion/`):

**Open-source (9)**: MikeOSS, GLAW, Lavern, JudicialMind, Lawgent,
Claude-Code-Law-Firm, Prism Legal OS, Legal Skills Open, QWED-Legal.

**Comerciales (6)**: LawPortal, case.dev, Lawgitech, Gotham, LawVu, NewMind.

## Roadmap V2.1

Ver sección 7 de la FICHA (`FICHA.md`): 13 features candidatas, incluyendo:
- Frontend Next.js + shadcn/ui (dashboard matter-centric + ⌘K command bar)
- Agentic citator con treatment labels (followed/distinguished/doubted/overruled/per_incuriam)
- Capa de rechazo determinista (estilo QWED) con DeadlineGuard para términos procesales colombianos
- Redline DOCX con tracked changes nativas
- RAG local con bge-m3 + Qdrant
- Practice-area playbooks (laboral, civil/familia, penal, migración, corporativo)
- MCP server público para integración con despachos externos
