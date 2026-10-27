# LEGAL — Despacho Jurídico Digital ALBRA V2.0

> Registro legal del proyecto. Atribución de inspiraciones y
> salvaguardas clean-room. Marcada cada casilla solo si es verdad.

## Identidad del proyecto

- **Nombre**: Despacho Jurídico Digital ALBRA
- **Versión**: V2.0
- **Stack**: Python 3.10+ · SQLite WAL · JSONL append-only · Markdown + YAML frontmatter · pytest
- **Licencia**: Apache 2.0 (compatible con reuso clean-room de Lavern, Legal-Skills-Open, QWED-Legal)
- **Repo**: github.com/ALBRA8/DESPACHO-JURIDICO
- **Commit base**: `1bcf829` (ARNÉS migration)
- **Commit V2.0**: <se llena al mergear>

## Inspiraciones (solo como referencia de funciones; no se copia nada)

### Open-source investigados (9)

| Proyecto | Repo | Licencia | Qué aportó como inspiración |
|---|---|---|---|
| MikeOSS | open-legal-products/mike | AGPL-3.0 | Matters como unidad central; tamper-evident exports (idea para V2.1) |
| GLAW | rikitrader/glaw | MIT | 9 hard gates; adversarial RED→BLUE pipeline (V2.1); organigrama explicito |
| Lavern | AnttiHero/lavern | Apache-2.0 | Human gates; Precedent Board (V2.2) |
| JudicialMind | judicialmind/legal-agents | MIT | Agent files en markdown; 3-Level Progressive Disclosure |
| Lawgent | WenzhuoXu/lawgent | MIT | Citation audit pre-reveal con round-trip de quotes |
| Claude-Code-Law-Firm | huodebing-alt/Claude-Code-Law-Firm | MIT | `minimum_human_signoff`; state machine monótono con AWAITING-PARTNER; audit JSONL por matter con retención 10 años |
| Prism Legal OS | FuturixAI-and-Quantum-Works/Prism-Legal-OS | AGPL-3.0 | Outbox pattern + leases (idea para V2.1 background jobs); AES-256-GCM para credenciales (V2.1) |
| Legal Skills Open | ThomasMoreAI/legal-skills-open | Apache-2.0 | SKILL.md con frontmatter (formato seguido en agentes V2.0) |
| QWED-Legal | QWED-AI/qwed-legal | Apache-2.0 | Capa de rechazo determinista (idea para V2.1 DeadlineGuard) |

### Comerciales investigados (6)

| Plataforma | URL | Qué aportó como inspiración |
|---|---|---|
| LawPortal | lawportal.ai | Cadena Suggest→Prepare→Approve→Execute→Record; 3 capas (Record/Agent/Governance) |
| case.dev | case.dev | 880+ skills como activo portable; MCP como estándar de facto |
| Lawgitech | lawgitech.eu | Multilingüismo real (no traducción automática) |
| Gotham | trygotham.io | Agentic citator con treatment labels (V2.1 feature diferenciadora); Court Formats print-ready |
| LawVu | lawvu.com | Saved Views compartibles (V2.1); Lens portfolio-wide risk analysis |
| NewMind | newmind.ai | 5-layer architecture (idea para Memory Cell como layer separada, V2.1) |

## Checklist de sala limpia

> Verificada para V2.0. Marcada cada casilla solo si es verdad.

- [x] Las funciones están descritas con palabras propias; no hay textos copiados de los 15 referentes originales.
- [x] No hay capturas, iconos, logos, sonidos ni imágenes de los 15 referentes en este proyecto.
- [x] No hay código, pseudocódigo ni nombres internos sacados de los informes de investigación.
- [x] El nombre (ALBRA) y la identidad visual son propios y no se confunden con ninguno de los 15 referentes.
- [x] Ninguna función se salta pagos, licencias, logins o protecciones de los referentes originales. Todos los patrones se recrean desde cero sobre el stack Python del proyecto ALBRA.
- [x] Las inspiraciones se citan explícitamente para atribución, pero la implementación es 100% original sobre el stack Python del proyecto ALBRA.

## Salvaguardas específicas

### Ética abogadil colombiana

- **Decreto 1967/2014** (Código Disciplinario Único abogados): cada acción sensible pasa por approval chain con `minimum_human_signoff` obligatorio. El agente no es autónomo para acciones finales.
- **Ley 1123/2007** (Régimen Disciplinario Abogado): audit log JSONL matter-scoped con hash chain tamper-evident. Retención 10 años alineada con expectativa de Tribunal Nacional Disciplinario.
- **Ley 1581/2012** (Habeas Data): datos personales del cliente guardados localmente en SQLite. Pendiente para V2.1: cifrado AES-256-GCM y filtro de hash antes de consultar fuentes externas.

### Anti-alucinación (fail-closed)

- **Pipeline citation audit**: extract → validate → retrace → reveal_or_block.
- **Sentencias rechazadas** explícitamente (C-251/2002, T-760/2008, AR-001/2020): si un LLM las cita, el sistema BLOCKA con reason claro al abogado.
- **Artículos no en corpus**: el agente NO revela respuesta. Marca `unverified` y pide confirmación manual.

### State machine monótono

- Una vez `FIRMADO-Y-ENTREGADO`, ninguna transición es posible.
- Única retrocesión permitida: `EN-ESPERA-DE-APROBACIÓN → BORRADOR-FINAL` (rechazo de aprobación → loop de retrabajo explícito). Esta retrocesión NO rompe el audit-trail porque persiste como transición auditable en `state_history`.

## Disclaimer obligatorio en drafts V2.0

Todo draft generado por DRAFTING-AGENT debe llevar al final del archivo:

> Este documento es un borrador generado por el agente ALBRA y requiere
> revisión y firma de un abogado calificado del despacho antes de su
> radicación. No constituye asesoría jurídica autónoma.

## Conflictos de interés

ALBRA V2.0 no incluye módulo de conflictos de interés. Pendiente para V2.1
con patrón de "Ethical walls por matter" (RBAC + matter-level access lists,
inspirado en Gotham y LawVu).

## Privacidad de datos

- **Local-only V2.0**: SQLite local, JSONL local, markdown local. Sin cloud.
- **V2.1**: AES-256-GCM para datos personales en SQLite con `ALBRA_DATA_KEY`.
- **V2.1**: Filtro de hash SHA-256 antes de buscar en fuentes públicas externas.

## Atribución final

- **Metodología**: ClonaKit (https://www.divisualproject.academy) — clean-room workflow FICHA → construir sin ver original.
- **ARNÉS migration**: commit `1bcf829` (general_adapter, harness/bridges/bootstrap).
- **V1.0-V1.6 hardening**: ALBRA project, 491 tests pre-V2.0.
- **V2.0 work**: este commit (fecha: 27 oct 2026).

## Exclusiones explícitas

- **Frontend**: V2.0 no tiene UI nativa (CLI only). Next.js + shadcn/ui queda para V2.1.
- **Integración LLM real**: el comando `albra research` en V2.0 hace citation audit sobre texto proporcionado directamente (sin invocar LLM). Integración con `albra.reasoning` queda para V2.1.
- **DOCX redline**: V2.0 no genera DOCX. Tracked changes nativas queda para V2.1.
- **RAG local**: V2.0 no tiene vector DB. Qdrant + bge-m3 queda para V2.1.
