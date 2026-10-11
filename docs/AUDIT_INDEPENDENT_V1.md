# INFORME DE AUDITORÍA INDEPENDIENTE
# COLOMBIA LEGAL KNOWLEDGE & RESEARCH V1.0
# Commit auditado: c65ca6a

## Resultado: ❌ AUDIT FAIL

Existen **3 hallazgos P0** (bloqueadores antes de cargar corpus).
La arquitectura existe pero está DESCONECTADA del organismo Runtime,
y dos bugs críticos en clasificación de autoridad/temporalidad pueden
producir resultados jurídicamente peligrosos.

---

## P0 — BLOQUEADORES

### P0-1. LegalKnowledgeEngine NO está cableado al Runtime (CRÍTICO)

**Hallazgo**: `LegalKnowledgeEngine` (albra/knowledge/legal_engine.py) existe
con pipeline completo (query → classification → retrieval → verification →
abstention → evidence → response), pero **NINGÚN código del agente o
Runtime lo invoca**.

**Evidencia**:
```
Agent.boot referencia LegalKnowledgeEngine?: False
Runtime.execute referencia LegalKnowledgeEngine?: False
```

Cuando el usuario pregunta `"¿Qué dice el artículo 25 de la Constitución?"`,
el agente responde con `provider_used="rules_fallback_legal"` y el texto
`"Detecto una consulta jurídica. Sin embargo... conocimiento jurídico aún
no ha sido cargado"` — **sin invocar el LegalKnowledgeEngine**.

**Riesgo**: Toda la arquitectura jurídica (12 módulos, 59 tests) está
DESCONECTADA del organismo vivo. Los tests del engine funcionan en aislamiento
pero el usuario nunca llega a ella.

**Acción requerida**:
- `Runtime.execute()` debe detectar consultas jurídicas (vía
  `LegalQueryClassifier` o detección de `legal_question` en reasoning) y
  delegar a `LegalKnowledgeEngine.query()`.
- El engine debe estar wired en `Agent.boot()` como órgano `legal_engine`.
- El `reasoning_engine.plan()` debe invocar el classifier y enrutar a
  `legal_engine` cuando la consulta sea jurídica.

### P0-2. `LegalVerifier._select_primary()` invierte jerarquía de fuentes

**Hallazgo**: El método `_select_primary()` en `verification.py:150-154`
utiliza `-c.source_tier` como clave de ordenación. Esto **invierte la
jerarquía**: una fuente S4 (secundaria) sortea PRIMERO que una S0 (primaria
superior).

**Evidencia**:
```
S0 score=0.4  vs  S4 score=0.95
primary_evidence_id: s4  (esperado s0)
```

La auditoría pedía explícitamente verificar que "una fuente S3/S4 no pueda
accidentalmente superar una fuente primaria simplemente por score semántico".
El bug hace exactamente esto.

**Por qué pasa**: `-SourceTier.S0_PRIMARY_SUPERIOR = 0`, `-SourceTier.S4_SECONDARY = -4`.
Al ordenar ascendente, `-4 < 0` → S4 sortea primero.

**Acción requerida**:
- Cambiar `-c.source_tier` por `c.source_tier` en `_select_primary()`.
- Agregar test específico: S0 con score bajo debe superar S4 con score alto.
- Re-verificar que el `primary_evidence_id` que se registra en EvidenceChain
  sea S0/S1 (no S4).

### P0-3. `is_vigente()` no reconoce status="historica" sin effective_until

**Hallazgo**: En `temporal.py:51-71`, la función `is_vigente()` solo
considera no-vigentes los statuses: `derogada, sustituida, inexequible,
nula, perdida_vigencia`. **"historica" no está en la lista**.

Si una norma se marca como `status="historica"` (porque se indexó una
versión histórica) pero `effective_until=None`, `is_vigente()` retorna
`True` — se considera vigente.

**Evidencia**:
```
is_vigente(status='historica', effective_from=None, effective_until=None)
→ True  (esperado False)
```

**Riesgo**: Una norma histórica puede aparecer como vigente en consultas
`current`. Si la ingestión carga versiones históricas sin `effective_until`
(pero con `status="historica"`), serán presentadas como vigentes.

**Acción requerida**:
- Agregar `"historica"` a la lista de statuses no-vigentes en `is_vigente()`.
- Agregar `"suspendida"` consideración más fina (si suspendida temporal,
  podría reactivarse — pero sin datos de reactivación, mejor no vigente).
- Validar status contra `VALIDITY_STATUS` controlado (no aceptar strings
  arbitrarios).

---

## P1 — CORRECCIONES IMPORTANTES

### P1-1. Modelo de precedente jurisprudencial simplificado (peligroso)

**Hallazgo**: `Jurisprudence.binding: bool = False` es **binario**. En
Colombia, los efectos jurídicos de las sentencias son más matizados:

| Tipo de sentencia | Efecto |
|---|---|
| Constitucionalidad AT (exequible) | erga omnes |
| Constitucionalidad IN (inexequible) | erga omnes |
| Constitucionalidad EX (exequible condicionado) | erga omnes |
| Sentencias de unificación (STC/AUG) | erga omnes |
| Sentencias de tutela C (revisión) | erga omnes |
| Sentencias comunes (casación) | inter partes |
| Autos | inter partes |

El modelo actual no puede distinguir `erga omnes` de `inter partes`.

**Acción requerida**:
- Reemplazar `binding: bool` por `effect: str` con valores controlados
  (`erga_omnes | inter_partes | intra_partes`).
- Agregar `scope: str` (nacional | departamental | municipal).
- Agregar `process_class: str` (constitucional | civil | penal | laboral |
  contencioso_administrativo).
- Normalizar `precedent_status` con vocabulario controlado:
  `vigente | superado | aclarado | modificado`.

**Sin corregir todavía**: reportado según instrucciones de auditoría.

### P1-2. Deduplicación de retrieval pierde artículos relevantes

**Hallazgo**: En `retrieval_providers.py:102-108`, la deduplicación es por
`source_id`. Como `source_id` se setea a `norm.id`, múltiples artículos de
la **misma norma** se consideran duplicados y solo pasa 1.

**Evidencia**:
```
3 artículos sobre "salud" en Ley 100 → solo se devuelve 1
total_found: 1 (esperado 3)
```

**Riesgo**: Si el usuario pregunta sobre un tema cubierto por múltiples
artículos de la misma norma, solo verá 1. Respuesta incompleta.

**Acción requerida**:
- Deduplicar por `(source_id, article_id)` o por `article_id` solo.
- O: deduplicar solo si `document_id` y `article_id` son iguales.

### P1-3. Filtro de jurisdicción para jurisprudencia roto

**Hallazgo**: En `retrieval_providers.py:188-194`:
```python
if query.jurisdiction and j.authority and query.jurisdiction != "CO":
    continue
```

La condición `query.jurisdiction != "CO"` solo filtra cuando la query **NO**
es CO. Para `query.jurisdiction="CO"` (default), **NUNCA se filtra** —
cualquier sentencia de cualquier país aparece en queries CO.

**Evidencia**:
```
sentencia argentina con jurisdiction=CO → aparece en query CO
total_found: 1 (esperado 0)
```

**Acción requerida**:
- Agregar campo `jurisdiction` a `Jurisprudence` (no existe).
- Comparar `j.jurisdiction != query.jurisdiction`.

### P1-4. `Ingestion.ingest()` no valida `authority` vacío

**Hallazgo**: En `ingestion.py:118-122`:
```python
if authority and not authority.strip():
    raise ValueError("authority required")
```

Si `authority=""`, la primera condición `if authority` es `False` → el
`raise` NUNCA se ejecuta. El documento se ingesta sin autoridad.

**Evidencia**:
```
sin authority: ok=True (esperado False)
```

**Acción requerida**:
- Cambiar a `if not authority or not authority.strip():`.

### P1-5. `ArticleResolver` es código muerto

**Hallazgo**: La clase `ArticleResolver` en `query_classifier.py:225-260`
no se invoca desde ningún lugar del engine (`engine usa ArticleResolver: False`).
La lógica de aclaración vive en `LegalQueryClassifier.classify()`.

**Acción requerida**:
- Eliminar `ArticleResolver` o integrarlo como parte de `LegalQueryClassifier`.
- Evitar dos implementaciones de la misma lógica.

### P1-6. `_article_to_candidate` usa `hasattr(norm, "source_id")` que siempre es False

**Hallazgo**: En `retrieval_providers.py:213`:
```python
source_id=norm.source_id if hasattr(norm, "source_id") else norm.id,
```

`Norm` schema NO tiene atributo `source_id` (ver `schemas.py:158-202`). El
`hasattr` siempre retorna `False` y siempre se usa `norm.id`. Código
engañoso/muerto.

**Acción requerida**:
- Eliminar el `hasattr` o agregar `source_id` a `Norm` schema (preferible
  eliminar — `norm.id` es suficiente).

### P1-7. Abstention checks orden subóptimo

**Hallazgo**: En `abstention.py:71-138`, el check de "ambiguous_query"
(4) se evalúa DESPUÉS de retrieval+verification. Si la query es ambigua,
se ejecuta retrieval innecesariamente (aunque `legal_engine.py:105` ya lo
detecta antes — pero el abstention policy no es idempotente).

**Acción requerida**:
- Mover "ambiguous_query" check al inicio de `evaluate()`.
- O: eliminar el check en abstention (ya está en legal_engine).

### P1-8. Búsqueda exacta NO respeta `source_tier`

**Hallazgo**: En `retrieval_providers.py:128-150`, `_exact_search` no
filtra por `query.source_tier`. Si pido "art 25 de la Constitución" con
`source_tier=S0_PRIMARY_SUPERIOR`, igual puedo recibir S3 si la norma
fue indexada en tier S3.

**Acción requerida**:
- Aplicar filtro `query.source_tier` en `_exact_search`.

### P1-9. `LegalKnowledgeEngine` no está wired al EvidenceChain en `Agent.boot()`

**Hallazgo**: Aunque `LegalKnowledgeEngine.__init__` acepta
`evidence_chain`, **nunca se le pasa en `Agent.boot()`** (porque no se
instancia el engine — ver P0-1).

**Acción requerida**:
- En `Agent.boot()` wirear `LegalKnowledgeEngine` con `EvidenceChain`
  y `HybridRetriever`.

---

## P2 — MEJORAS POSTERIORES

### P2-1. Regex `NORM_PATTERN_NAMED` no captura "Código Sustantivo del Trabajo"

Solo captura `código \w+` — el segundo token. "Código Sustantivo del
Trabajo" se trunca a "Código Sustantivo".

### P2-2. `Norm` no tiene `source_id` pero `Article` sí

Inconsistencia: Article no tiene `source_id`, Norm no tiene `source_id`.
Pero `EvidenceCandidate.source_id` se setea con `norm.id` (workaround).

### P2-3. `VersionHistory.get_version_at` asume formato ISO de fecha

Si `effective_from` no es ISO (string mal formado), `date.fromisoformat`
falla con `ValueError`. No hay try/except.

### P2-4. `LegalResponseBlock` no valida `content_type`

Acepta cualquier string. Debería validar contra `CONTENT_TYPES`.

### P2-5. `_select_primary` no considera `binding`

Para jurisprudencia, una decisión `binding=True` con score bajo debería
superar a `binding=False` con score alto. No hay lógica para esto.

### P2-6. `Sources` tienen URLs vacías — no hay validación

`COLOMBIA_OFFICIAL_SOURCES` declaran URLs vacías `""`. Si en el futuro
se cargan con URLs inválidas, no hay validación.

### P2-7. `Ingestion.ingest()` no valida `source_url`

Solo valida `raw_content` vacío. `source_url=""` pasa sin error.

### P2-8. `LegalQueryClassifier` no detecta "código sustantivo del trabajo"

`NORM_PATTERN_NAMED = (c[oó]digo\s+\w+)` solo captura 2 palabras.
"Código Sustantivo del Trabajo" no se captura completo.

### P2-9. Tests no cubren el caso de "norma histórica aparece como vigente"

El test `test_was_vigente_before_derogation` cubre derogación. Pero NO
cubre el caso `status="historica" + effective_until=None` (el bug P0-3).

### P2-10. `Conflict.kind` no valida contra lista controlada

Acepta cualquier string en `kind` y `severity`.

---

## A. Arquitectura verificada

| Módulo | Implementado | Conectado a Runtime | Conectado a Reasoning |
|---|---|---|---|
| schemas.py | ✅ | N/A (datos) | N/A |
| temporal.py | ✅ | ❌ (no invocado) | ❌ |
| sources.py | ✅ | ❌ | ❌ |
| retrieval.py | ✅ | ❌ (vía engine que no se invoca) | ❌ |
| retrieval_providers.py | ✅ | ❌ | ❌ |
| ingestion.py | ✅ | ❌ (no invocado desde boot) | ❌ |
| verification.py | ✅ | ❌ | ❌ |
| query_classifier.py | ✅ | ❌ | ❌ |
| citation.py | ✅ | ❌ | ❌ |
| abstention.py | ✅ | ❌ | ❌ |
| legal_provenance.py | ✅ | ❌ | ❌ |
| legal_engine.py | ✅ | **❌ NO CABLEADO** | **❌ NO CABLEADO** |

**Conclusión**: Los 12 módulos están implementados y tienen tests, PERO
no están integrados al organismo vivo. Solo funcionan en aislamiento.

## B. Modelo jurídico verificado

| Concepto | Implementado | Notas |
|---|---|---|
| fuente | ✅ | `OfficialSource` con S0-S4 |
| documento | ✅ | `LegalDocument` |
| norma | ✅ | `Norm` con metadata completa |
| artículo | ✅ | `Article` con embedding separada |
| disposición | ⚠️ | No hay separación explícita artículo/disposición |
| jurisprudencia | ⚠️ | `binding: bool` simplificado (ver P1-1) |
| doctrina | ✅ | `Doctrine` con source_tier S3 |
| versión | ✅ | `version: int + supersedes_id/superseded_by_id` |
| vigencia | ⚠️ | Bug con status="historica" (P0-3) |
| relación normativa | ✅ | `modifying_norm_ids, modified_by_norm_ids` |
| evidencia | ✅ | `EvidenceCandidate` con provenance |

## C. Temporalidad verificada

| Operación | Funciona | Notas |
|---|---|---|
| ¿Qué decía la norma en X? | ✅ | `is_vigente(when=date)` |
| ¿Qué dice actualmente? | ✅ (con bug) | Bug si status="historica" (P0-3) |
| ¿Cuándo entró en vigor? | ✅ | `effective_from` |
| ¿Fue derogada? | ✅ | `status="derogada" + effective_until` |
| ¿Norma histórica como vigente? | ❌ | Bug confirmado |

## D. Precedente/jurisprudencia verificado

| Concepto | Implementado |
|---|---|
| precedent | ✅ `precedent_status: str` (no controlado) |
| binding | ⚠️ `binding: bool` (binario, ver P1-1) |
| erga omnes | ❌ No modelado explícitamente |
| ratio decidendi | ✅ |
| obiter dicta | ✅ |
| citas | ✅ `cites_jurisprudence_ids` |
| autoridad judicial | ✅ `court` |
| relaciones | ✅ `reversed_by_id, reaffirms_id, distinguishes_id` |

**Simplificación peligrosa**: `binding: bool` no distingue efectos jurídicos
reales (erga omnes vs inter partes). Ver P1-1.

## E. Retrieval verificado

| Modo | Funciona |
|---|---|
| EXACT | ✅ (sin filtro tier — P1-8) |
| SEMANTIC | ✅ (con bug de jurisdicción P1-3) |
| METADATA filtering | ✅ (authority, source_tier, jurisdiction) |
| TEMPORAL | ✅ (current, historical, as_of) |
| JURISDICTION | ⚠️ Bug en jurisprudencia (P1-3) |
| HYBRID ranking | ✅ (`_rank` correcto) PERO `_select_primary` roto (P0-2) |

**Escenario donde S4 supera S0**: confirmado en runtime.

## F. Provenance verificado

- ✅ `LegalProvenance` con 10 campos completos
- ✅ Integración con `EvidenceChain.add()` vía `record_evidence_with_provenance`
- ⚠️ Pero el `primary_evidence_id` que se registra puede ser S4 (bug P0-2)
- ⚠️ Rehidratación EvidenceChain funciona, pero el provenance registrado puede apuntar al candidato equivocado

## G. EvidenceChain verificado

- ✅ Rehidratación tras restart funciona
- ✅ `record_evidence_with_provenance` integra correctamente
- ⚠️ Solo se invoca si `verification.primary_evidence_id` (que puede estar mal por P0-2)

## H. Ingestion verificado

- ✅ Pipeline 14 pasos implementado
- ❌ No valida `authority=""` (P1-4)
- ⚠️ No valida `source_url=""` (P2-7)
- ✅ Rechaza `raw_content=b""`
- ✅ Warning si `document_type` no en catálogo
- ✅ Calcula content_hash
- ✅ Registra provenance

## I. Security verificado

- ✅ No hay bypass directo al vector store
- ✅ Provider no expone `admin_retrieve` o `bypass_guard`
- ⚠️ **PERO** el `LegalKnowledgeEngine` no está en el pipeline Runtime,
  así que cuando se conecte, hay que asegurarse que:
  - Toda invocación del engine pase por ExecutionGuard.
  - No se pueda llamar `engine.query()` directamente sin Runtime.
  - No haya método `bypass_runtime` o `direct_query`.

## J. Tests verificados

| Versión | Tests | Lint |
|---|---|---|
| Python 3.10 | ✅ 332/332 PASS | ✅ All checks passed |
| Python 3.11 | ✅ 332/332 PASS | ✅ All checks passed |
| Python 3.12 | ✅ 332/332 PASS | ✅ All checks passed |

**PERO**: Los tests no cubren los bugs P0 encontrados:
- No hay test que verifique que S0 supera S4 en select_primary.
- No hay test que verifique status="historica" no vigente.
- No hay test que verifique que agent.process() invoca LegalKnowledgeEngine.

Tests están pasando pero **no detectan los bugs** porque prueban componentes
en aislamiento, no la integración.

## K. Capacidades pendientes

- ❌ `LegalKnowledgeEngine` NO integrado al Runtime (P0-1)
- ❌ Filtro jurisdicción jurisprudencia roto (P1-3)
- ❌ Validación authority vacío (P1-4)
- ❌ Modelo binding erga_omnes/inter_partes (P1-1)
- ❌ Corpus jurídico real cargado (esperado - fase posterior)
- ❌ Embeddings reales (hash embedding fallback)
- ❌ Backend de búsqueda externa (Research framework preparado)
- ❌ Especialistas operativos (CATALOG ONLY)
- ❌ MSP (NOT IMPLEMENTED)
- ❌ VLM/ASR/LLM real conectado

## L. Riesgos

### Riesgos críticos
1. **Al cargar corpus**, el engine no se invocará — el usuario seguirá
   recibiendo "conocimiento no cargado" aunque el corpus esté cargado.
2. **Al cargar corpus S0 + S4 juntos**, una fuente secundaria S4 puede
   superarse a S0 en `primary_evidence_id` registrado en EvidenceChain.
3. **Versiones históricas** pueden aparecer como vigentes si no se setea
   `effective_until`.

### Riesgos jurídicos
1. Tratar sentencia inter_partes como si fuera erga_omnes (P1-1).
2. Mezclar jurisprudencia de otras jurisdicciones en queries CO (P1-3).

## M. Recomendación final

### ❌ AUDIT FAIL

**NO CARGAR CORPUS hasta cerrar los 3 hallazgos P0**.

### Plan de cierre requerido (P0 — antes de corpus)

1. **P0-1**: Wire `LegalKnowledgeEngine` a `Runtime.execute()` para que
   consultas jurídicas pasen por el pipeline jurídico (no por reasoning
   fallback).
2. **P0-2**: Corregir `_select_primary()` — cambiar `-c.source_tier` por
   `c.source_tier`. Agregar test S0-supera-S4.
3. **P0-3**: Agregar `"historica"` a la lista de statuses no-vigentes en
   `is_vigente()`. Agregar test.

### Plan de cierre recomendado (P1 — antes o durante corpus)

1. P1-1: Reemplazar `binding: bool` por `effect: str` (erga_omnes/inter_partes).
2. P1-2: Fix deduplicación por `article_id` (no solo `source_id`).
3. P1-3: Agregar `jurisdiction` a `Jurisprudence` + fix filtro.
4. P1-4: Fix `if not authority or not authority.strip()`.
5. P1-5: Eliminar `ArticleResolver` (dead code) o integrarlo.
6. P1-8: Agregar filtro `source_tier` en `_exact_search`.
7. P1-9: Wire `EvidenceChain` a `LegalKnowledgeEngine`.

### Test suite a reforzar

- Tests que prueben `agent.process("consulta jurídica")` invoca
  `LegalKnowledgeEngine.query()`.
- Tests que prueben S0 con score bajo supera S4 con score alto.
- Tests que prueben status="historica" sin effective_until NO es vigente.
- Tests que prueben jurisprudencia argentina NO aparece en query CO.
- Tests que prueben deduplicación NO pierde artículos de la misma norma.

---

## RESUMEN EJECUTIVO

- **Tests**: 332/332 en Python 3.10/3.11/3.12 + lint PASS
- **Arquitectura**: 12 módulos implementados, 59 tests, PERO **DESCONECTADOS**
  del Runtime. Funcionan en aislamiento, no en producción.
- **3 hallazgos P0** (bloqueadores):
  1. LegalKnowledgeEngine no cableado al Runtime
  2. _select_primary invierte jerarquía S0/S4
  3. status="historica" sin effective_until se considera vigente
- **8 hallazgos P1** (importantes antes/durante corpus)
- **10 hallazgos P2** (mejoras posteriores)
- **Recomendación**: ❌ AUDIT FAIL → CIERRE DE HALLAZGOS P0 antes de
  CORPUS INGESTION.

La arquitectura está preparada conceptualmente pero la integración con el
organismo vivo es inexistente. Los tests pasan pero no prueban la integración.
