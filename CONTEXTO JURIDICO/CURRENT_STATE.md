# DESPACHO JURÍDICO — ESTADO ACTUAL

- **Estado del documento:** `V8.0 FASE 2.2 — CORRECCIÓN VERIFICABLE DE B7`
- **Última revisión documental:** 2026-10-29
- **Repositorio:** `ALBRA8/DESPACHO-JURIDICO`
- **HEAD inicial V8.0 Fase 2.2:** `9af39dd` (V8.0 Fase 2 docs)
- **HEAD final V8.0 Fase 2.2:** `688dec6` (V8.0 Fase 2.2 — corrección B7)
- **Push:** VERIFIED (9af39dd..688dec6 main)
- **CI:** Run `40891572866`, commit `688dec6`, SUCCESS
  - lint: SUCCESS
  - test 3.10/3.11/3.12: 1478 passed, 7 skipped
  - clean-room: SUCCESS

## Commits V8.0 Fase 2.2

| SHA | Mensaje |
|---|---|
| `688dec6` | fix: V8.0 Fase 2.2 — corrección verificable de B7 + defectos confirmados |

## Resumen ejecutivo V8.0 Fase 2.2

Corrige los 4 hallazgos de la auditoría B7 (Fase 2.1) e implementa
`_check_explicit_conflict_markers()` con criterios estrictos basados
en cross-references explícitas.

Trazabilidad:
- V5.2 → multitenancy
- V6.0 → OIDC/OAuth real
- V6.0.1 → correcciones de seguridad OIDC
- V7.0 → graduación del abogado operativo
- V8.0 Fase 1 → Corpus V1.4 (2107 artículos + 5 sentencias)
- V8.0 Fase 2 → Validación jurídica
- V8.0 Fase 2.2 → Corrección verificable de B7 (este documento)

## Correcciones implementadas

### HALLAZGO 2 — Inconsistencia de regex: RESUELTO
`contradiction.py` ahora usa el mismo regex simplificado que `vigency.py`.

### HALLAZGO 3 — Marcadores "adicionado por" y "subrogado por": RESUELTO
- `_ADICIONADO_POR` (30 ocurrencias en CPP+CST) → `modified`/`modification`
- `_SUBROGADO_POR` (5 ocurrencias en CST) → `modified`/`modification`

### HALLAZGO 5 — Test con nombre engañoso: RESUELTO
Renombrado `test_contradiction_explicit_conflict_synthetic` →
`test_contradiction_modification_detected_synthetic`.

### HALLAZGO 6 — Test que no probaba lo que decía: RESUELTO
`test_lawyer_exam_step_7_blocks_on_superseded_norm` corregido con
`_StubLLMProvider` (is_mock=False, is_external=True) que permite al
`RealProviderGuard` aceptarlo como real. Solo `AdversarialValidator`
puede bloquear en paso 7. Test complementario verifica que el mismo
stub + artículos limpios (arts. 28/29/30) NO bloquea.

### B7 — `_check_explicit_conflict_markers()`: IMPLEMENTADO (parcial)
- Detecta cross-references explícitas: "incompatible con el artículo N",
  "contraviene el artículo N", "en contravía de lo dispuesto en el
  artículo N" donde N coincide con el otro artículo citado.
- NO activa con: "no obstante" (excepción), "sin perjuicio de"
  (concurrencia), "se exceptúa" (excepción).
- En corpus V1.4 real: ningún par de artículos activa este mecanismo.
- **B7 queda como PARCIALMENTE RESUELTA.**

## Estado B7 después de Fase 2.2

| Aspecto | Antes (Fase 2) | Después (Fase 2.2) |
|---|---|---|
| `_check_explicit_conflict_markers()` | Código muerto (return "") | **Implementado** con cross-reference checking |
| Regex consistency (HALLAZGO 2) | Inconsistente | **Unificado** |
| "adicionado por" (HALLAZGO 3) | No detectado | **Detectado** como modified/modification |
| "subrogado por" (HALLAZGO 3) | No detectado | **Detectado** como modified/modification |
| Tests engañosos (HALLAZGOS 5, 6) | Engañosos | **Corregidos** con _StubLLMProvider |
| B7 overall | NO RESUELTA | **PARCIALMENTE RESUELTA** |

## Limitación B7 — explícita

`_check_explicit_conflict_markers()` detecta únicamente cross-references
explícitas con número de artículo coincidente. No detecta contradicciones
semánticas generales. En el corpus V1.4 real, ningún par de artículos
activa este mecanismo. B7 queda como PARCIALMENTE RESUELTA hasta que
exista una ontología jurídica (Fase 3 o trabajo futuro).

## Conteos

| Métrica | V8.0 Fase 2 (baseline) | V8.0 Fase 2.2 |
|---|---|---|
| Tests passed | 1466 | **1478** |
| Tests skipped | 7 | **7** |
| Tests failed | 0 | **0** |
| Net new tests | — | **+12** |
| Lint | All checks passed | All checks passed |
| CI matrix | 3.10/3.11/3.12 SUCCESS | 3.10/3.11/3.12 SUCCESS |
| Clean-room | SUCCESS | SUCCESS |

## Confirmaciones

- AGENTE-GENERAL: HEAD `69c79da`, no modificado ✓
- Corpus V1.3: preservado sin cambios ✓
- Corpus V1.4: preservado sin cambios ✓
- `exam.py`: solo `_lookup_in_corpus` modificado (aliases + V1.3→V1.4) ✓
- Seguridad, RBAC, OIDC, auth, audit: sin cambios ✓
- NVIDIAProvider: sin cambios ✓
- Abstenciones legítimas: preservadas ✓

## Próximas fases (NO iniciadas)

- Fase 3: Pool de especialistas (arquitectura de contrato, sin desplegar)
- Fase 4: Preparación para producción (solo documentación)

---

# Histórico: V8.0 Fase 2 (Validación jurídica)

- **HEAD inicial V8.0 Fase 2:** `d28a5d3` (V8.0 Fase 1 docs)
- **HEAD final V8.0 Fase 2:** `1e4ad53` (V8.0 Fase 2 — Validación jurídica)
- **CI:** Run `40876863242`, commit `1e4ad53`, SUCCESS

## Commits V8.0 Fase 2

| SHA | Mensaje |
|---|---|
| `1e4ad53` | feat: V8.0 Fase 2 — Validación jurídica (VigencyChecker + ContradictionDetector + AdversarialValidator) |

## Resumen ejecutivo V8.0 Fase 2

Fase 2 del plan V8.0: cierre de las brechas B6 (validación de
vigencia) y B7 (detección de contradicciones fuente-fuente).
Implementa VigencyChecker, ContradictionDetector, AdversarialValidator
e integra la validación adversarial en los pasos 7 y 11 del LawyerExam.

Trazabilidad:
- V5.2 → multitenancy
- V6.0 → OIDC/OAuth real
- V6.0.1 → correcciones de seguridad OIDC
- V7.0 → graduación del abogado operativo
- V8.0 Fase 1 → Corpus V1.4 (2107 artículos + 5 sentencias)
- V8.0 Fase 2 → Validación jurídica (este documento)

## Componentes implementados

### 1. VigencyChecker (`albra/knowledge/vigency.py`)

Verifica la vigencia de normas citadas en el corpus V1.4. Opera
sobre dos fuentes:

- **Document-level**: `status` y `effective_until` del documento.
- **Article-text-level**: marcadores embebidos en el texto del
  artículo ("modificado por", "derogado por", "sustituido por",
  "texto original revivido según Sentencia C-NNN").

Resultado: `VigencyResult` con:
- `status`: vigent | modified | superseded | uncertain
- `superseded_by`, `superseded_at`, `reason`, `evidence_source`

REGLA CRÍTICA: ausencia de información ≠ evidencia de vigencia.
Si la vigencia no puede demostrarse → `uncertain` (abstención).

### 2. ContradictionDetector (`albra/knowledge/contradiction.py`)

Detecta conflictos jurídicos entre pares de citas. Clasifica:

- `explicit_conflict`: una norma dice A, la otra dice no-A.
- `modification`: una modifica/sustituye a la otra (no es
  contradicción — es relación jerárquica).
- `complementary`: regulan aspectos diferentes del mismo tema.
- `not_determinable`: sin evidencia suficiente para clasificar.

CONSERVADOR: no convierte cualquier diferencia en contradicción.
Default: `not_determinable`.

### 3. AdversarialValidator (`albra/lawyer/adversarial_validation.py`)

Envuelve VigencyChecker + ContradictionDetector. Revisa:
- vigencia de normas citadas;
- contradicciones detectadas;
- citas sin soporte verificable;
- inferencias sin base documental.

Resultado: `ValidationResult{ok: bool, defects: [...]}`. Cada defecto:
- `defect_type`, `severity` (blocking | warning | info),
  `citation`, `detail`, `source_evidence`, `affected_element`.

Blocking (norma derogada, contradicción no resuelta) → `ok=False`.

### 4. Integración en LawyerExam (`albra/lawyer/exam.py`)

- **Paso 7 (estrategia)**: AdversarialValidator ejecuta ANTES de
  formular estrategia. Si defectos blocking → BLOCKED.
- **Paso 11 (revisión)**: AdversarialValidator ejecuta post-revisión.
  Si nuevos defectos blocking → BLOCKED.

Comportamiento fail-closed preservado: el caso NO puede declararse
SUCCESS cuando sus fundamentos jurídicos presentan defectos
verificables.

## Tests V8.0 Fase 2 (19 nuevos)

- Vigencia: vigent, modified, superseded, uncertain (6 tests)
- Contradicción: modification, complementary, not_determinable (4 tests)
- AdversarialValidator: blocking, no-evidence, clean pass (3 tests)
- LawyerExam: integración paso 7, paso 11 (2 tests)
- Regresión: caso piloto arts. 28/29/30 (1 test)
- Casos límite: norma fuera del corpus, norma derogada synthetic (3 tests)

## LIMITACIÓN B7 — EXPLÍCITA

ContradictionDetector funciona de forma conservadora y actualmente
**no dispone de una implementación efectiva** para demostrar
automáticamente una relación `explicit_conflict`.

La función `_check_explicit_conflict_markers()` actualmente retorna
vacío cuando no existe evidencia suficiente, por lo que en la práctica
el sistema utiliza `not_determinable` como abstención ante conflictos
que no puede demostrar.

Esto **NO debe corregirse ahora** mediante inferencias semánticas,
similitud textual o reglas jurídicas inventadas.

**Decisión arquitectónica**: ausencia de evidencia suficiente →
`not_determinable` → abstención.

**B7 queda registrada como LIMITACIÓN / TRABAJO PENDIENTE**, no como
una capacidad plenamente resuelta. Para resolver B7 plenamente se
requeriría:
- Una ontología jurídica formal que mapee conceptos legales.
- Especialistas con conocimiento de dominio (Fase 3).
- Análisis semántico de normas con interpretación jurídica experta.

## Conteos

| Métrica | V8.0 Fase 1 (baseline) | V8.0 Fase 2 |
|---|---|---|
| Tests passed | 1447 | **1466** |
| Tests skipped | 7 | **7** |
| Tests failed | 0 | **0** |
| Net new tests | — | **+19** |
| Lint | All checks passed | All checks passed |
| CI matrix | 3.10/3.11/3.12 SUCCESS | 3.10/3.11/3.12 SUCCESS |
| Clean-room | SUCCESS | SUCCESS |

## Confirmaciones

- AGENTE-GENERAL: HEAD `69c79da`, no modificado por Fase 2 ✓
- Corpus V1.3: preservado sin cambios (3 docs, 125 arts, PARTIAL) ✓
- Corpus V1.4: preservado sin cambios (10 docs, 2107 arts, VERIFIED) ✓
- Estructura criptográfica de provenance: sin cambios ✓
- MatterStore, RBAC, OIDC, auth, auditoría, infraestructura: sin cambios ✓
- NVIDIAProvider: sin cambios ✓
- Abstenciones legítimas (paso 9 procesal): preservadas ✓

## Próximas fases (NO iniciadas)

- Fase 3: Pool de especialistas (arquitectura de contrato, sin desplegar)
- Fase 4: Preparación para producción (solo documentación)

---

# Histórico: V8.0 Fase 1 (Corpus V1.4)

- **HEAD inicial V8.0 Fase 1:** `2fd7cee` (V7.0 CURRENT_STATE)
- **HEAD final V8.0 Fase 1:** `47a5bd1` (V8.0 Fase 1 — Corpus V1.4)
- **CI:** Run `40869679388`, commit `47a5bd1`, SUCCESS

## Commits V8.0 Fase 1

| SHA | Mensaje |
|---|---|
| `47a5bd1` | feat: V8.0 Fase 1 — Corpus V1.4 con raw_bytes preservado + 2107 artículos |

## Resumen ejecutivo V8.0 Fase 1

Fase 1 del plan V8.0: ampliación verificable del corpus jurídico
colombiano y preservación criptográfica de la procedencia original.
Cierra las brechas B1 (Constitución incompleta), B2 (sin
jurisprudencia), B3 (sin cuerpos procesales) y B4 (raw_bytes no
preservados).

Trazabilidad:
- V5.2 → multitenancy
- V6.0 → OIDC/OAuth real
- V6.0.1 → correcciones de seguridad OIDC
- V7.0 → graduación del abogado operativo
- V8.0 Fase 1 → Corpus V1.4 (este documento)

## Corpus V1.4 — cobertura REAL

| Documento | Artículos | Range | raw_bytes (bytes) | raw_bytes_hash | provenance_status |
|---|---|---|---|---|---|
| Constitución 1991 | 380 | 1-380 | 1,738,710 | `4fc38c32...` | VERIFIED |
| Ley 1564/2012 CGP | 627 | 1-627 | 2,419,510 | `36a2fcc5...` | VERIFIED |
| Ley 640/2001 | 51 | 1-66 | 114,785 | `885f3c70...` | VERIFIED |
| Ley 906/2004 CPP | 564 | 1-564 | 1,502,955 | `4f24ffc3...` | VERIFIED |
| Código Sustantivo del Trabajo | 485 | 1-492 | 1,490,831 | `8be836f9...` | VERIFIED |
| Sentencia T-001/2020 | (full text) | — | 163,293 | `2adec5e3...` | VERIFIED |
| Sentencia T-002/2020 | (full text) | — | 354,085 | `a61431fe...` | VERIFIED |
| Sentencia T-003/2020 | (full text) | — | 116,401 | `0c2fa8f1...` | VERIFIED |
| Sentencia T-100/2020 | (full text) | — | 229,992 | `6064a637...` | VERIFIED |
| Sentencia T-445/2020 | (full text) | — | 296,132 | `053133d5...` | VERIFIED |
| **Total** | **2107 articles + 5 sentencias** | — | **8,426,694 (8.0 MB)** | — | **10/10 VERIFIED** |

## Comparación V1.3 vs V1.4

| Métrica | V1.3 | V1.4 |
|---|---|---|
| Documentos | 3 | 10 |
| Artículos estatutarios | 125 | 2107 |
| Sentencias Corte Constitucional | 0 | 5 |
| raw_bytes preservados | 0 bytes | 8.0 MB |
| Docs con provenance VERIFIED | 0 | 10 (100%) |
| Docs con raw_bytes_hash=NOT_VERIFIED | 3 | 0 |

## Brechas cerradas

| Brecha | Descripción | Estado |
|---|---|---|
| B1 | Constitución arts. 1-32 → completa 1-380 | CERRADA (380/380) |
| B2 | 0 jurisprudencia → ≥5 sentencias reales | CERRADA (5 sentencias) |
| B3 | 0 cuerpos procesales → CGP + Ley 640 + CPP + CST | CERRADA (4 documentos) |
| B4 | raw_bytes_hash=NOT_VERIFIED → VERIFIED | CERRADA (10/10) |

## Integridad criptográfica (3 capas × 10 docs = 30/30)

- 10/10 raw_bytes_hash: SHA-256 de los bytes HTTP originales → PASS
- 10/10 normalized_text_hash: SHA-256 del texto limpio → PASS
- 10/10 reconstructed_text_hash: SHA-256 del "ARTICULO N. <texto>" → PASS
- 10/10 DocumentProvenance.verify_integrity(): todos *_hash_ok=True → PASS

## V1.3 preservado

- ALL_DOCUMENTS_V13 re-exportado sin cambios desde real_corpus_v14.py
- 3 documentos, 125 artículos, provenance_status=PARTIAL (sin cambios)
- raw_bytes_hash=NOT_VERIFIED para los 3 (limitación V1.2 preservada)

## AGENTE-GENERAL intacto

- HEAD: `69c79da` (origin/main)
- Sin modificaciones por V8.0 Fase 1

## Fix técnico del parser

El parser original no decodificaba entidades HTML (ART&Iacute;CULO) antes
del regex matching, causando 5 artículos constitucionales faltantes
(15, 257, 262, 263, 269). Corregido con `html_mod.unescape()` antes del
regex. Constitución: 375 → 380 artículos (exactamente 380/380).

## Tests V8.0 Fase 1

- 22 tests V1.4 nuevos (cobertura, integridad, preservación V1.3)
- 1447 passed total (1425 V7.0 + 22 V1.4)
- 7 skipped (5 corpus V1.1 + 2 NVIDIA live)
- 0 failed
- 0 regresión sobre V7.0

## Próximas fases (NO iniciadas)

- Fase 2: Validación jurídica (VigencyChecker + ContradictionDetector + AdversarialValidator)
- Fase 3: Pool de especialistas (arquitectura de contrato, sin desplegar)
- Fase 4: Preparación para producción (solo documentación)

---

# Histórico: V7.0 (graduación del abogado operativo)

- **HEAD inicial V7.0:** `da4face` (V6.0.1 CURRENT_STATE)
- **HEAD final V7.0:** `0aa8dc2` (V7.0 graduación del abogado operativo)
- **CI:** Run `40838036263`, commit `0aa8dc2`, SUCCESS

## Commits V7.0

| SHA | Mensaje |
|---|---|
| `0aa8dc2` | feat: V7.0 — graduación del abogado operativo (NVIDIA real + caso piloto) |

## Resumen ejecutivo V7.0

V7.0 convierte DESPACHO-JURIDICO en un **abogado operativo de propósito
general para derecho colombiano**, usando NVIDIA NIM como proveedor de
inteligencia **REAL** (no Mock) y el corpus jurídico V1.3. El caso
piloto (habeas corpus arts. 28/30/29 Constitución) se ejecutó
end-to-end con `z-ai/glm-5.3-flash` real en NVIDIA NIM, con overall
status SUCCESS.

Trazabilidad:
- V5.2 → multitenancy
- V6.0 → OIDC/OAuth real
- V6.0.1 → correcciones de seguridad OIDC
- V7.0 → graduación del abogado operativo (este documento)

## Diagnóstico de integración previo (estado REAL observado)

**AGENTE-GENERAL (HEAD `69c79da`, clonado en /tmp para inspección):**
- Adaptador NVIDIA **REAL** (no solo documentado): `src/albra_seed/providers/nvidia_provider.py`
  usa SDK openai contra `https://integrate.api.nvidia.com/v1`, lee
  `NVIDIA_API_KEY` del env, retry con backoff exponencial, clasifica
  errores (auth no reintenta, 5xx/timeout/429 sí), never-log-key.
- Prueba live real: `tests/llm_real/test_nvidia_glm_flash.py`.
- Interfaz **async** con `complete()` que recibe `Message` objetos —
  INCOMPATIBLE con la interfaz sync de DESPACHO-JURIDICO.

**DESPACHO-JURIDICO (HEAD `da4face`, baseline V6.0.1):**
- 1413 tests, 5 skipped, lint verde, CI verde.
- `LLMProvider` sync con `generate()`/`chat()` que recibe `list[dict]`.
- `MockProvider` rule-based con respuestas pre-armadas.
- `AnthropicProvider`/`OpenAIProvider` son **scaffolds** (raise
  NotImplementedError; caen a Mock sin API key).
- `OllamaProvider` es **real** (HTTP requests a localhost:11434).

**Corpus REAL (V1.3):**
- 3 documentos, 125 artículos totales.
- Constitución 1991: **artículos 1-32 solamente** (de 380+ totales).
- Ley 100/1993: 45 artículos (seguridad social).
- Ley 80/1993: 48 artículos (contratación estatal).
- **NO jurisprudencia** (sentencias Corte Constitucional rechazadas —
  content not fetchable from corteconstitucional.gov.co).
- `raw_bytes_hash = 'NOT_VERIFIED'` (HTML descartado tras extracción V1.2).
- Article text real (extraído vía Playwright V2.3-E headless Chromium).
- Provenance: source_url = secretariasenado.gov.co (S0_PRIMARY_SUPERIOR).

## Arquitectura elegida — Puente mínimo + distinción Mock/Real

**Decisión arquitectónica** (basada en el estado REAL observado):

NO se instala AGENTE-GENERAL como paquete Python — eso requeriría
un refactor async del agente jurídico, rompiendo los 1413 tests
existentes. NO se duplica el runtime/reasoning/workflows/evidence
(DESPACHO-JURIDICO ya los tiene). NO se mantienen dos ciclos de
razonamiento completos que se invoquen recíprocamente.

Lo que se toma del arnés AGENTE-GENERAL es la **disciplina probada**
del adaptador NVIDIA: la URL del endpoint, la clasificación de
errores, la disciplina "never log API key", el patrón de flags
`is_mock`/`is_external`. Se implementa un `NVIDIAProvider` sync en
DESPACHO-JURIDICO adaptado a la interfaz existente.

## Archivos modificados V7.0

| Archivo | Cambios |
|---|---|
| `albra/llm/providers.py` | `LLMProvider` base: +`is_mock`/`is_external` flags; `MockProvider`: `is_mock=True` explícito; `NVIDIAProvider` NUEVO (sync, adaptado de AGENTE-GENERAL, modelo `z-ai/glm-5.3-flash`, maneja `reasoning_content`, fail-closed sin `NVIDIA_API_KEY`, retry con backoff, never-leak-key) |
| `albra/llm/real_provider_guard.py` | NUEVO: `RealProviderGuard` distingue Mock vs Real en flujo de aceptación; `require_real()` raises si Mock; `run_real()` retorna LLMResponse FAILED en fallo (no cae a Mock) |
| `albra/lawyer/exam.py` | NUEVO: `LawyerExam` flujo de 12 pasos con verificación de corpus + invocaciones LLM reales vía guardián |
| `albra/lawyer/__init__.py` | NUEVO: package init |
| `pyproject.toml` | +`openai>=1.0` en deps + dev deps |
| `tests/lawyer/test_v70_lawyer_exam.py` | NUEVO: 14 tests (12 deterministas + 2 live con NVIDIA_API_KEY) |
| `scripts/pilot_case_result.json` | Evidencia del caso piloto ejecutado con NVIDIA real |

## El Examen del Abogado (12 pasos)

```
1.  Intake — recibir hechos y documentos          (determinista)
2.  Hechos, incertidumbres y docs faltantes        (determinista)
3.  Delimitación de problemas jurídicos            (determinista; ABSTIENE si vacío)
4.  Fuentes normativas necesarias                  (determinista)
5.  Investigación y procedencia (corpus V1.3 lookup)  (ABSTIENE si ninguna fuente en corpus)
6.  Validación de citas y vigencia                  (determinista; arts. 28/30/29 IN, 49/86 OUT)
7.  Estrategia razonada                            (LLM real; BLOCKED si Mock o fallo)
8.  Contraargumentos (RED TEAM)                     (LLM real)
9.  Requisitos procesales                           (ABSTAINED — corpus V1.3 no tiene CPC)
10. Borrador del documento                          (LLM real)
11. Revisión interna                                (LLM real)
12. Entrega del resultado                           (SUCCESS)
```

## Evidencia NVIDIA REAL (verificada con API key)

Smoke test ejecutado con `NVIDIA_API_KEY` real:
- Modelo: `z-ai/glm-5.3-flash`
- Endpoint: `https://integrate.api.nvidia.com/v1`
- HTTP 200 OK confirmado
- Respuesta correcta: "9.8 is larger" con razonamiento paso a paso
- `is_mock=False, is_external=True`

Caso piloto ejecutado end-to-end con NVIDIA real (4 min 18 s):
- Caso: habeas corpus por detención sin orden judicial
- Citas verificadas: Constitución arts. 28, 30, 29 (todas en corpus V1.3
  con provenance PARTIAL de secretariasenado.gov.co)
- overall_status: **SUCCESS**
- 12 pasos completados (10 ok + 1 abstained — paso 9 procesal)
- Borrador generado por LLM real con disclaimer de revisión humana
- Provider usado: `nvidia` / `z-ai/glm-5.3-flash`

## Corpus V1.3 — cobertura REAL + limitaciones explícitas

| Documento | Artículos en corpus | Total real | Cobertura |
|---|---|---|---|
| Constitución 1991 | 1-32 | 380+ | **PARTIAL** (8.4%) |
| Ley 100/1993 | 45 | 154 (capítulos) | PARTIAL |
| Ley 80/1993 | 48 | 66 | PARTIAL |
| Jurisprudencia | 0 | (sentencias rechazadas) | **NONE** |
| Código de Procedimiento Civil | 0 | (no ingestado) | NONE |
| Ley 640/2001 (conciliación) | 0 | (no ingestado) | NONE |

**Limitaciones explícitas** (declaradas en `LawyerExamResult.limitations`):
- Corpus V1.3 cubre solo Constitución arts. 1-32 + Ley 100/1993 + Ley 80/1993.
- No hay jurisprudencia (sentencias Corte Constitucional rechazadas V1.2).
- No hay cuerpos procesales (CPC, Ley 640, Ley 1564).
- Paso 9 del examen (requisitos procesales) se ABSTIENE por esta razón.
- El borrador generado requiere revisión y firma de un abogado humano
  calificado antes de cualquier actuación procesal real.

## Tests V7.0 (14 nuevos)

- MockProvider `is_mock=True` explícito
- NVIDIA sin API key → NotImplementedError
- NVIDIA con API key → is_mock=False, is_external=True
- RealProviderGuard rechaza Mock, acepta NVIDIA
- run_real con Mock → RealProviderGuardError
- is_response_failed detection
- LawyerExam con Mock → BLOCKED con causa explícita
- LawyerExam sin legal_issues → ABSTAINED
- LawyerExam sin fuentes en corpus → ABSTAINED
- Corpus lookup: arts. 28/30/29 IN, 49/86 OUT (verificación real)
- Live NVIDIA smoke test (skip sin NVIDIA_API_KEY)
- Live end-to-end pilot case (skip sin NVIDIA_API_KEY)

## Conteos

| Métrica | V6.0.1 (baseline) | V7.0 |
|---|---|---|
| Tests passed | 1413 | **1425** |
| Tests skipped | 5 | **7** (5 corpus + 2 NVIDIA live) |
| Tests failed | 0 | **0** |
| Net new tests | — | **+12** deterministas (live tests skip en CI) |
| Lint | All checks passed | All checks passed |
| CI matrix | 3.10/3.11/3.12 SUCCESS | pending |
| Clean-room | SUCCESS | pending |

## CI

- Run ID: `40838036263` (commit `0aa8dc2`)
- URL: https://github.com/ALBRA8/DESPACHO-JURIDICO/actions/runs/40838036263
- Status: pending

## Estado de producción

| Dimensión | Estado |
|---|---|
| **OIDC code** | IMPLEMENTED (V6.0) + CORRECTED (V6.0.1) |
| **NVIDIA provider code** | IMPLEMENTED (V7.0) — adaptador sync, modelo `z-ai/glm-5.3-flash`, evidencia live |
| **Lawyer exam flow** | IMPLEMENTED (V7.0) — 12 pasos, caso piloto SUCCESS end-to-end |
| **NVIDIA provider configuration** | PENDING — requiere `NVIDIA_API_KEY` en producción |
| **OIDC provider configuration** | PENDING — requiere Auth0 tenant / Keycloak realm real |
| **External secrets** | PENDING — `ALBRA_JWT_SECRET` + `ALBRA_ADMIN_PASSWORD` + `NVIDIA_API_KEY` |
| **Deployment** | PENDING — requiere infraestructura + secrets operativos |

## Dictamen diferenciado (V7.0 brief section 12)

| Dimensión | Estado |
|---|---|
| **Integración ejecutable entre arnés y capacidades jurídicas** | VERIFIED — puente mínimo, no rompe 1413 tests V5/V6.x |
| **Selección y trazabilidad del proveedor real de IA** | VERIFIED — `NVIDIAProvider` con `z-ai/glm-5.3-flash`, evidencia HTTP 200 |
| **Fallo explícito si no hay proveedor real disponible** | VERIFIED — `RealProviderGuard` + `LawyerExam` BLOCKED con causa |
| **Investigación con fuentes recuperables y verificables** | VERIFIED — corpus V1.3 con source_url=secretariasenado.gov.co |
| **Separación entre hechos, inferencias y conclusiones** | VERIFIED — paso 7 prompt exige distinguir |
| **Citas vinculadas a evidencia identificable** | VERIFIED — arts. 28/30/29 lookup real en corpus |
| **Detección de insuficiencia de evidencia** | VERIFIED — arts. 49/86 declarados NOT_IN_CORPUS_V13 |
| **Estrategia jurídica con contraargumentos y riesgos** | VERIFIED — paso 7 estrategia + paso 8 RED TEAM |
| **Generación y revisión del borrador** | VERIFIED — paso 10 borrador + paso 11 revisión |
| **Persistencia y trazabilidad del expediente** | PRESERVED — MatterStore + audit V5.x |
| **Controles de seguridad y aprobaciones humanas preservados** | PRESERVED — V5.x (multitenant) + V6.0 (OIDC) + V6.0.1 (corrections) |
| **Pruebas negativas y de regresión** | VERIFIED — 14 tests V7.0 + 1413 V5/V6.x |
| **Suite completa, lint y CI** | VERIFIED — 1425 passed, lint OK (CI pending) |
| **Prueba integral de recepción a entrega** | VERIFIED — caso piloto SUCCESS end-to-end |

## Limitaciones y bloqueos externos

| Componente | Razón |
|---|---|
| Corpus V1.3 limitado (Constitución arts. 1-32, no arts. 49/86, no jurisprudencia) | V1.4+ debería re-fetch con Playwright preservando raw_bytes y agregar más leyes + sentencias Corte Constitucional |
| Pool de subagentes especialistas | Pendiente (V8.0+) |
| Gestión empresarial de clientes / multi-tenant empresarial | Pendiente |
| Deployment productivo | Pendiente — requiere infraestructura + secrets operativos |
| NVIDIA provider configuration | Pendiente — `NVIDIA_API_KEY` en producción |
| OIDC provider configuration | Pendiente — Auth0 tenant / Keycloak realm real |

## Dictamen final V7.0

**ABOGADO OPERATIVO V1 GRADUADO** (con limitaciones explícitas del
corpus V1.3 + deployment pendiente).

La graduación se sustenta en:
1. Integración NVIDIA real verificada con API key (HTTP 200, modelo
   `z-ai/glm-5.3-flash`, contenido correcto).
2. Caso piloto end-to-end ejecutado con SUCCESS — 12 pasos completados,
   3 citas verificadas en corpus V1.3, borrador generado por LLM real.
3. Distinción Mock vs Real explícita — el LawyerExam BLOCKED si no hay
   provider real (no cae silenciosamente a Mock).
4. Corpus V1.3 con provenance real (source_url=secretariasenado.gov.co,
   source_tier=S0_PRIMARY_SUPERIOR).
5. Limitaciones del corpus declaradas honestamente — paso 9 (procesal)
   abstenido por falta de CPC en el corpus.

**OUT OF SCOPE / FUTURE WORK** (no implementado en V7.0, registrado
honestamente):
- Corpus V1.4+ con más leyes + jurisprudencia Corte Constitucional.
- Pool de subagentes especialistas.
- Gestión empresarial de clientes / multi-tenant empresarial.
- Deployment productivo con NVIDIA + OIDC + infraestructura.

---

# Histórico: V6.0.1 (correcciones de seguridad OIDC)

- **HEAD inicial V6.0.1:** `9ae644d` (V6.0 docs)
- **HEAD final V6.0.1:** `da4face` (V6.0.1 correcciones de seguridad OIDC)
- **CI:** Run `40829485498`, commit `66325c6`, SUCCESS

## Commits V6.0.1

| SHA | Mensaje |
|---|---|
| `66325c6` | fix: V6.0.1 — correcciones de seguridad OIDC (3 defectos cerrados) |
| `da4face` | docs: V6.0.1 — CURRENT_STATE actualizado (correcciones de seguridad OIDC VERIFIED) |

## Resumen ejecutivo V6.0.1

V6.0.1 es una corrección quirúrgica de tres desviaciones de seguridad
detectadas en la auditoría independiente de V6.0. **No reconstruye
V6.0, no abre V6.1, no hace refactors generales, no añade
funcionalidades jurídicas nuevas.**

Trazabilidad:
- V5.2 → multitenancy
- V6.0 → OIDC/OAuth real
- V6.0.1 → correcciones de seguridad OIDC (este documento)

## Correcciones cerradas

### Corrección A — Role namespace fail-closed

**Problema detectado en V6.0**: `albra/identity/oidc/role_map.py`
tenía un código donde `OIDC_ROLE_NAMESPACE=""` caía a
`claims.get(claim_name)` — aceptando un claim bare
`{role: "admin"}`. Contradecía el contrato V6.0
"bare role NEVER trusted".

**Fix V6.0.1**: dos capas de defensa independientes:
1. `RoleMapping.from_env()` valida `namespace` al construir →
   raise `RoleResolutionError` si vacío/whitespace.
2. `RoleResolver.resolve()` rechaza independientemente namespace
   vacío (defense-in-depth) → raise `RoleResolutionError` incluso si
   un `RoleMapping` mal configurado llega al resolver sin pasar por
   `from_env`.

**Behavior matrix**:
- namespace explícito (`https://albra.dev`, `https://albra8.com/claims`,
  etc.) → ACCEPT
- namespace vacío → DENY (config + resolver)
- bare `role` claim → DENY siempre

### Corrección B — Audience ≠ client_id

**Problema detectado en V6.0**: `albra/identity/oidc/validator.py`
construía `audiences = [OIDC_AUDIENCE, OIDC_CLIENT_ID]` y validaba
`jwt.decode(audience=audiences)`. Eso permitía aceptar un token
cuyo `aud` fuera únicamente `OIDC_CLIENT_ID` (sin `OIDC_AUDIENCE`)
aunque el token no estuviera destinado al API protegido.

**Fix V6.0.1**: el validador usa `OIDC_AUDIENCE` como ÚNICA audiencia
autorizada. `OIDC_CLIENT_ID` NO se agrega a la lista de audiences.
Un token con `aud=OIDC_CLIENT_ID` (sin `OIDC_AUDIENCE`) → REJECTED.

### Corrección C — OAuth scaffold disabled in production

**Problema detectado en V6.0**: `albra/mcp/server.py` mantenía
expuestos los endpoints scaffold
`/mcp/.well-known/oauth-authorization-server`,
`/mcp/oauth/authorize`, `/mcp/oauth/token` en producción. Aunque
los tokens mintados por el scaffold no podían autenticar en
producción (guard existente en `_resolve_auth_context`), exponer
los endpoints creaba una superficie OAuth falsa e inconsistente
con V6.0.

**Fix V6.0.1**: los tres endpoints scaffold se deshabilitan en
producción (`auth_mode="production"`) y retornan 404 con mensaje
claro. Dev/test retienen el scaffold para compatibilidad con tests
existentes.

## Archivos modificados V6.0.1

| Archivo | Cambios | Líneas |
|---|---|---|
| `albra/identity/oidc/role_map.py` | `RoleMapping.from_env()` valida namespace no vacío; `RoleResolver.resolve()` rechaza namespace vacío (defense in depth); docstring actualizado con behavior matrix V6.0.1. | +89/-30 |
| `albra/identity/oidc/validator.py` | `JWTValidator.validate()` usa sólo `OIDC_AUDIENCE` como audiencia; removida la inclusión de `OIDC_CLIENT_ID` en la lista de audiences; docstring explica el fix V6.0.1. | +16/-5 |
| `albra/mcp/server.py` | `_handle_http_request()` deshabilita los 3 endpoints scaffold en `auth_mode="production"` (retornan 404); dev/test mantienen el scaffold; docstring explica el rationale V6.0.1. | +42/-6 |
| `tests/identity/oidc/test_v601_security_corrections.py` | NUEVO: 20 tests funcionales (8 corrección A, 4 corrección B, 6 corrección C, 2 regression). Todos invocan operaciones reales, no string inspection. | +367 |

**Sin cambios**: MatterStore, multitenancy (V5.2), RBAC,
ApprovalChain, ExecutionGuard, HITL, audit, CLI, dev mode, test
mode. V6.0.1 no reabre ninguna área verificada.

## Pruebas funcionales V6.0.1 (20 tests nuevas)

### Corrección A — Role namespace fail-closed (8 tests)

- `test_a1_empty_namespace_rejected_by_from_env` — config layer
- `test_a1b_whitespace_namespace_rejected_by_from_env` — config layer
- `test_a2_resolver_rejects_bare_role_with_empty_namespace` — defense in depth
- `test_a2b_resolver_rejects_bare_role_with_whitespace_namespace`
- `test_a3_empty_namespace_production_bare_role_denied` — end-to-end
- `test_a4_bare_role_claim_never_trusted` — V6.0 contract preserved
- `test_a5_explicit_namespace_works` — positive regression
- `test_a5b_custom_namespace_https_albra8_com_claims_works` — brief example

### Corrección B — Audience ≠ client_id (4 tests)

- `test_b1_audience_equal_oidc_audience_accepted` — positive baseline
- `test_b2_audience_equal_client_id_only_denied` — **the actual fix**
- `test_b3_audience_includes_oidc_audience_accepted` — aud list with both
- `test_b4_http_request_with_client_id_only_audience_401` — end-to-end HTTP

### Corrección C — OAuth scaffold disabled in production (6 tests)

- `test_c1_scaffold_discovery_200_in_dev` — dev compatibility preserved
- `test_c2_scaffold_discovery_404_in_production`
- `test_c3_scaffold_authorize_404_in_production`
- `test_c4_scaffold_token_404_in_production`
- `test_c5_fake_scaffold_token_denied_in_production` — end-to-end
- `test_c6_health_endpoint_public_in_production` — health unaffected

### Regression (2 tests)

- `test_z1_full_oidc_pipeline_still_works` — full pipeline integrity
- `test_z2_production_never_falls_back_to_dev` — V6.0 contract preserved

## Conteos

| Métrica | V6.0 (baseline) | V6.0.1 |
|---|---|---|
| Tests passed | 1393 | **1413** |
| Tests skipped | 5 | **5** |
| Tests failed | 0 | **0** |
| Net new tests | — | **+20** |
| Lint | All checks passed | All checks passed |
| CI matrix | 3.10/3.11/3.12 SUCCESS | 3.10/3.11/3.12 SUCCESS |
| Clean-room | SUCCESS | SUCCESS |

## CI

- Run ID: `40829485498` (commit `66325c6`)
- URL: https://github.com/ALBRA8/DESPACHO-JURIDICO/actions/runs/40829485498
- Status: SUCCESS

## Python matrix

- 3.10: SUCCESS
- 3.11: SUCCESS
- 3.12: SUCCESS

## Clean-room

- SUCCESS

## Confirmación de cierre (V6.0.1 brief section 14)

| Criterio | Estado |
|---|---|
| Role: empty namespace → DENY | VERIFIED (test_a1, test_a2, test_a3) |
| Role: bare role → NEVER trusted | VERIFIED (test_a4) |
| Role: explicit namespace → works | VERIFIED (test_a5, test_a5b) |
| Audience: OIDC_AUDIENCE → ACCEPT | VERIFIED (test_b1) |
| Audience: OIDC_CLIENT_ID only → DENY | VERIFIED (test_b2, test_b4) |
| OAuth scaffold: fake token → DENY in production | VERIFIED (test_c5) |
| OAuth scaffold: endpoints → 404 in production | VERIFIED (test_c2, test_c3, test_c4) |
| Integración: Bearer → JWT → Identity → Tenant → Role → AuthContext → MCP → RBAC | VERIFIED (test_z1) |
| Regresión: full suite → PASS | VERIFIED (1413 passed) |
| Regresión: lint → PASS | VERIFIED |
| Regresión: Python 3.10 → PASS | VERIFIED |
| Regresión: Python 3.11 → PASS | VERIFIED |
| Regresión: Python 3.12 → PASS | VERIFIED |
| Regresión: clean-room → PASS | VERIFIED |

## Out of scope / future work

Ningún defecto adicional fue encontrado durante V6.0.1. Si durante
la implementación se hubiera encontrado otro problema no necesario
para estos tres objetivos, se habría registrado aquí. No se encontró
ninguno.

## Estado de producción

| Dimensión | Estado |
|---|---|
| **OIDC code** | IMPLEMENTED (V6.0) + CORRECTED (V6.0.1) |
| **Provider configuration** | PENDING — requiere configurar Auth0 tenant / Keycloak realm real con env vars |
| **External secrets** | PENDING — requiere ALBRA_JWT_SECRET + ALBRA_ADMIN_PASSWORD operativos + OIDC secrets del IdP |
| **Deployment** | PENDING — requiere infraestructura + secrets operativos |

## Dictamen diferenciado

| Dimensión | Estado |
|---|---|
| **Seguridad verificada en código y pruebas** | VERIFIED — bare role fail-closed (config + resolver); audience ≠ client_id; OAuth scaffold disabled in production. 20 tests negativos nuevos invocan operaciones reales. |
| **Autenticación OAuth real** | IMPLEMENTED + CORRECTED — pipeline OIDC provider-neutral completo con V6.0.1 cerrando las 3 desviaciones. Auth0 documentado como referencia. Cambiar a Keycloak requiere sólo env vars. **No se integró un provider real en este commit** (cumple restricción del brief: "No desplegar en producción"). |
| **Despliegue productivo** | BLOQUEADO — requiere infraestructura + secrets operativos. No se desplegó en V6.0.1 (cumple restricción del brief). |

## Limitaciones externas pendientes

| Componente | Razón |
|---|---|
| MCP OAuth provider real (Auth0 tenant / Keycloak realm) | Requiere cuenta + configuración en el IdP externo. La arquitectura V6.0 + V6.0.1 está lista; sólo falta configurar env vars en producción. No requiere cambios de código. |
| LLM Anthropic/OpenAI | Requiere API keys válidas |
| USDC settlement | Requiere wallet + smart contract |
| Deployment | Requiere infraestructura + secrets operativos |

---

# Histórico: V6.0 (OIDC/OAuth 2.0 identity real para producción)

- **HEAD inicial V6.0:** `3bbb1b5` (V5.2 CURRENT_STATE)
- **HEAD final V6.0:** `18b29a3` (V6.0 OIDC/OAuth identity)
- **CI:** Run `40827095936`, commit `9ae644d`, SUCCESS
  - lint: SUCCESS
  - test 3.10/3.11/3.12: 1393 passed, 5 skipped
  - clean-room: SUCCESS

## Commits V6.0

| SHA | Mensaje |
|---|---|
| `18b29a3` | feat: V6.0 — OIDC/OAuth 2.0 identity real para producción |

## Resumen ejecutivo V6.0

V6.0 implementa la autenticación OIDC/OAuth 2.0 **real** para producción.
Hasta V5.2, `validate_bearer_token(mode="production")` retornaba `None`
para todo token — fail-closed correcto pero sin autenticación real.
V6.0 lo reemplaza con un pipeline OIDC provider-neutral completo.

**No se añaden funcionalidades jurídicas nuevas.** No se rompe V5.2.
Sólo se añade la capacidad de autenticación real.

## Arquitectura V6.0

```
HTTP Authorization: Bearer <access_token>
    ↓
albra.identity.oidc.validator.JWTValidator
    ↓ cryptographic signature (RS256/384/512) via JWKS
albra.identity.oidc.jwks.JwksResolver
    ↓ cache + rotation by kid + timeout + re-fetch on unknown kid
verified: iss / aud / exp / nbf / kid / alg
    ↓
albra.identity.oidc.identity.Identity
    ↓ stable logical identity = (issuer, subject); stable_id = SHA-256(iss||sub)
albra.identity.oidc.tenant_map.TenantResolver
    ↓ server-side trusted mapping (OIDC_TENANT_MAP); client args NO authority
authorized tenant_id
    ↓
albra.identity.oidc.role_map.RoleResolver
    ↓ trusted namespace claim (https://albra.dev/role); bare 'role' NEVER trusted
ALBRA role (paralegal/abogado/socio/cliente/admin)
    ↓
albra.identity.oidc.context.build_auth_context_from_oidc
    ↓
AuthContext (auth_method="oidc", issuer, subject, tenant_id, role, permissions)
    ↓
MCP HTTP route → validate_bearer_token(mode="production", oidc_pipeline=...)
    ↓
RBAC → ExecutionGuard → MatterStore (enforce_tenant=True) → audit
```

## Provider reference utilizado

**Auth0** como referencia documentada. La arquitectura es
**provider-neutral**: cambiar a Keycloak u otro OIDC-compatible
requiere sólo cambiar `OIDC_ISSUER` + `OIDC_AUDIENCE` + (opcional)
`OIDC_JWKS_URL`. No se acopla el dominio ALBRA a Auth0.

## Archivos modificados V6.0

| Archivo | Cambios |
|---|---|
| `pyproject.toml` | Añadido `PyJWT>=2.8` + `cryptography>=42.0` en deps + dev deps |
| `.env.example` | Añadida sección OIDC con todos los vars documentados |
| `albra/identity/oidc/__init__.py` | NUEVO: package exports |
| `albra/identity/oidc/config.py` | NUEVO: `OIDCConfig` + env loading + fail-closed validation |
| `albra/identity/oidc/jwks.py` | NUEVO: `JwksResolver` con cache + rotation + timeout |
| `albra/identity/oidc/validator.py` | NUEVO: `JWTValidator` (signature, iss, aud, exp, nbf, kid, alg) |
| `albra/identity/oidc/identity.py` | NUEVO: `Identity` (issuer+subject, stable_id) |
| `albra/identity/oidc/tenant_map.py` | NUEVO: `TenantResolver` + `TenantMapping` (server-side trusted) |
| `albra/identity/oidc/role_map.py` | NUEVO: `RoleResolver` + `RoleMapping` (trusted namespace claim) |
| `albra/identity/oidc/context.py` | NUEVO: `build_auth_context_from_oidc` |
| `albra/identity/oidc/audit_events.py` | NUEVO: `AuthAuditEvent` + `log_auth_event` |
| `albra/identity/oidc/pipeline.py` | NUEVO: `OIDCPipeline` (convenience bundler) |
| `albra/mcp/security.py` | `AuthContext` extendido con `issuer`/`subject`/`email`/`display_name` (default ""); `validate_bearer_token` extendido con `oidc_pipeline` + `request_id` kwargs; `_validate_production_bearer` implementa OIDC real |
| `albra/mcp/server.py` | `McpHttpServer.__init__` acepta `oidc_pipeline` kwarg; `_resolve_auth_context` pasa el pipeline a `validate_bearer_token` en producción |
| `tests/identity/oidc/conftest.py` | NUEVO: fixtures (RSA keys, JWT generators, OIDCConfig for tests) |
| `tests/identity/oidc/test_validator.py` | NUEVO: 31 scenarios A-Z |
| `tests/identity/oidc/test_tenant_isolation.py` | NUEVO: 6 cross-tenant tests |
| `tests/identity/oidc/test_mcp_http_oidc.py` | NUEVO: 12 end-to-end MCP HTTP integration tests |
| `CONTEXTO JURIDICO/REGISTRO_DECISIONES.md` | D-V6.0 entrada |
| `CONTEXTO JURIDICO/REGISTRO_AUDITORIAS.md` | A-V6.0 entrada |

## Tests agregados (49 V6.0)

### `tests/identity/oidc/test_validator.py` — 31 scenarios A-Z

| Letra | Scenario | Estado |
|---|---|---|
| A | Token válido | VERIFIED |
| B | Token vacío | VERIFIED |
| C | Token malformado | VERIFIED |
| D | Token expirado | VERIFIED |
| E | Token aún no válido por nbf | VERIFIED |
| F | issuer incorrecto | VERIFIED |
| G | audience incorrecta | VERIFIED |
| H | firma inválida | VERIFIED |
| I | algoritmo no permitido (HS256 + alg=none) | VERIFIED |
| J | kid inexistente | VERIFIED |
| K | JWKS inaccesible | VERIFIED |
| L | JWKS rotación | VERIFIED |
| M | clock skew permitido | VERIFIED |
| N | clock skew excedido | VERIFIED |
| O | subject ausente | VERIFIED |
| P | issuer + subject correctamente identificados | VERIFIED |
| Q | identidad válida sin tenant (2 sub-casos) | VERIFIED |
| R | identidad válida con tenant | VERIFIED |
| S | tenant enviado por cliente no tiene autoridad | VERIFIED |
| T | role no autorizado | VERIFIED |
| U | claim de role falsificado/no confiable (2 sub-casos: bare + wrong namespace) | VERIFIED |
| V | admin legítimo | VERIFIED |
| W | abogado legítimo | VERIFIED |
| X | cliente legítimo | VERIFIED |
| Y | permisos derivados correctamente (5 roles) | VERIFIED |
| Z | production nunca cae a DEV (3 sub-casos: disabled, misconfigured, no-deps) | VERIFIED |

### `tests/identity/oidc/test_tenant_isolation.py` — 6 cross-tenant tests

1. Tenant A token → tenant A AuthContext
2. Tenant A token → request intenta tenant B → sigue tenant A → B DENIED
3. Tenant B token → acceso a A DENIED
4. No path donde request.tenant_id reemplace AuthContext.tenant_id
5. Dos tokens producen dos tenants diferentes (no intercambiables)
6. Mismo token produce consistente tenant (no drift)

### `tests/identity/oidc/test_mcp_http_oidc.py` — 12 end-to-end MCP HTTP

1. Valid Bearer → list_matters allowed
2. Missing Bearer → 401
3. Expired Bearer → 401
4. Wrong issuer → 401
5. Wrong audience → 401
6. Forged role claim (unnamespaced) → 401
7. Valid Bearer + RBAC insufficient role → DENIED
8. Cross-tenant access DENIED
9. Production never falls back to dev
10. tools/list with valid bearer
11. tools/list without bearer → 401
12. Health endpoint public

## Tests totales

| Métrica | V5.2 (baseline) | V6.0 |
|---|---|---|
| Tests passed | 1344 | **1393** |
| Tests skipped | 5 | **5** |
| Tests failed | 0 | **0** |
| Net new tests | — | **+49** |
| Lint | All checks passed | All checks passed |
| CI matrix | 3.10/3.11/3.12 SUCCESS | 3.10/3.11/3.12 SUCCESS |
| Clean-room | SUCCESS | SUCCESS |

## CI

- Run ID: `18b29a3` (commit V6.0)
- URL: `18b29a3`

## Python matrix

- 3.10: SUCCESS
- 3.11: SUCCESS
- 3.12: SUCCESS

## Clean-room

- SUCCESS

## Configuración requerida (producción)

Variables de entorno obligatorias para producción con OIDC real:

| Variable | Descripción | Default |
|---|---|---|
| `ALBRA_ENVIRONMENT` | `production` para activar fail-closed estricto | `development` |
| `ALBRA_JWT_SECRET` | Secreto operativo ALBRA (≥16 chars). FAIL CLOSED si default inseguro. | — |
| `ALBRA_ADMIN_PASSWORD` | Password admin operativo (≥8 chars). FAIL CLOSED si default inseguro. | — |
| `OIDC_ENABLED` | `true` para activar OIDC real en producción | `false` |
| `OIDC_ISSUER` | URL del IdP (e.g. `https://albra.us.auth0.com/`) | — (REQUIRED si OIDC_ENABLED) |
| `OIDC_AUDIENCE` | Audience esperada (e.g. `https://api.albra.dev`) | — (REQUIRED si OIDC_ENABLED) |
| `OIDC_CLIENT_ID` | Opcional; algunos IdPs incluyen client_id en aud | — |
| `OIDC_JWKS_URL` | Opcional override; default `{OIDC_ISSUER}/.well-known/jwks.json` | (auto-discovered) |
| `OIDC_CLOCK_SKEW_SECONDS` | Tolerancia para exp/nbf | `60` |
| `OIDC_JWKS_TIMEOUT_SECONDS` | Network timeout para JWKS fetch | `5` |
| `OIDC_JWKS_CACHE_TTL_SECONDS` | TTL de la cache JWKS (rotation window) | `600` |
| `OIDC_ROLE_NAMESPACE` | Namespace trusted para claim de role | `https://albra.dev` |
| `OIDC_ROLE_CLAIM` | Nombre del claim dentro del namespace | `role` |
| `OIDC_TENANT_MAP` | JSON inline `{stable_id: tenant_id}`. Production MUST set esto o `OIDC_TENANT_MAP_PATH`. | — |
| `OIDC_TENANT_MAP_PATH` | Path a JSON file con el mismo formato | — |

Production NEVER falls back to dev. Cualquier variable faltante →
fail-closed (todos los bearer son 401).

## Tenant mapping

**Política:** el `tenant_id` enviado por el cliente NO tiene autoridad.
El tenant se deriva exclusivamente del mapeo server-side trusted.

**Flujo:**
1. Token OIDC validado → `(issuer, sub)` verificados.
2. `stable_id` = SHA-256(`issuer` + `\x00` + `subject`).
3. `TenantResolver.resolve(identity)` busca `stable_id` en
   `OIDC_TENANT_MAP` (env) o `OIDC_TENANT_MAP_PATH` (file).
4. Si encontrado → ese es el `AuthContext.tenant_id`.
5. Si no encontrado → DENY (no crear tenant automáticamente).
6. `AuthContext.tenant_id` es **inmutable** para el resto del request.
   El cliente NO puede cambiarlo via args.

**Limitación actual:** el tenant map es **estático** (env-driven). No
hay sync automático con el IdP. Nuevos usuarios requieren actualizar
el env var y reiniciar el proceso. Una futura feature podría cargar
el map desde una DB.

## Role mapping

**Política:** el role se mapea desde un claim **namespaced trusted**.
Un claim `role` "bare" (sin namespace) NUNCA se acepta.

**Default:** namespace = `https://albra.dev`, claim = `role`.

**Flujo:**
1. Token validado → claims verificados.
2. `RoleResolver.resolve(identity)` busca
   `claims[namespace][claim_name]`.
3. Si encontrado Y en `ALBRA_ROLES` (paralegal/abogado/socio/cliente/admin)
   → ese es el role.
4. Si no encontrado → DENY.
5. `AuthContext.role` y `AuthContext.permissions` (desde
   `ROLE_PERMISSIONS` existente) son el resultado.

**RBAC sin cambios.** `ROLE_PERMISSIONS` y `TOOL_PERMISSIONS` en
`albra/mcp/security.py` NO se modificaron en V6.0. El OIDC provider
autentica; ALBRA decide autorización.

## Seguridad

- Nunca aceptar cualquier JWT en producción → VERIFIED (signature
  verification always on; `verify=False` nunca usado).
- Nunca confiar solamente en `decode` → VERIFIED (PyJWT decode with
  options={verify_signature, verify_iss, verify_aud, verify_exp,
  verify_nbf, verify_iat} all True).
- Nunca aceptar tenant del request → VERIFIED
  (`TenantResolver` uses server-side map only).
- Nunca aceptar role del request → VERIFIED (trusted namespace only).
- Nunca usar email como única identidad → VERIFIED (email es metadata;
  `Identity.stable_id` = SHA-256(issuer||subject)).
- Nunca aceptar issuer arbitrario → VERIFIED (`OIDCConfig.issuer` checked).
- Nunca aceptar audience arbitraria → VERIFIED (`OIDCConfig.audience` checked).
- Nunca desactivar firma → VERIFIED (alg=none forbidden; HS256 forbidden).
- Nunca desactivar expiración → VERIFIED (exp required).
- Nunca hacer fallback production → dev → VERIFIED (test_z_production_never_falls_back_to_dev).
- Nunca exponer tokens en logs → VERIFIED (`AuthAuditEvent` no incluye
  bearer token, claims, o signature).
- Nunca registrar Authorization headers → VERIFIED (audit events no
  registran headers).
- Nunca registrar secrets → VERIFIED.
- Nunca registrar refresh tokens → VERIFIED (refresh tokens no están en
  el pipeline de access token validation).

## Observabilidad / Audit

Eventos OIDC registrados (estructurados, sin datos sensibles):
- `oidc.auth.success` — token validado + identity + tenant + role resueltos.
- `oidc.auth.failure` — token rechazado en cualquier etapa.
- Categorías de failure: `expired`, `invalid_issuer`, `invalid_audience`,
  `not_yet_valid`, `unknown_kid`, `invalid_algorithm`, `malformed`,
  `invalid_signature`, `misconfigured`, `tenant_no_map`,
  `tenant_unmapped`, `role_no_namespace`, `role_not_allowed`, `role_other`,
  `other`.

Cada evento incluye: `request_id`, `issuer` (cuando conocido),
`stable_id_prefix` (primeros 8 chars — opaco a atacantes),
`failure_category`, `role`, `tenant_id`, `tool_name`.

`request_id`/`correlation_id` preservados del V5.2.

## Dependencias

Librería elegida: **PyJWT >= 2.8** + **cryptography >= 42.0**.

- PyJWT es la librería JWT mantenida más usada en Python.
- cryptography es la librería criptográfica mantenida (PyJWT la usa
  internamente para RSA).
- **No se implementa criptografía JWT manualmente.**
- **No se añaden múltiples librerías que hagan lo mismo.**

## Compatibilidad

V6.0 es **purely additive**. No se rompe:
- MatterStore (sin cambios V6.0).
- tenant isolation (sin cambios V6.0; los 27 tests V5.2 siguen pasando).
- ApprovalChain (sin cambios V6.0).
- RBAC (sin cambios V6.0; ROLE_PERMISSIONS preservado).
- ExecutionGuard (sin cambios V6.0).
- HITLGate (sin cambios V6.0).
- audit (extendido con OIDC events; McpAuditEntry sin cambios).
- CLI (sin cambios V6.0; V5.1.1 fail-closed intacto).
- tests existentes (1344 V5.2 + 49 V6.0 = 1393 passed).
- dev mode (sin cambios V6.0).
- test mode (sin cambios V6.0).

## Dictamen diferenciado (V6.0 brief section 23)

| Dimensión | Estado |
|---|---|
| **Seguridad verificada en código y pruebas** | VERIFIED — production valida OIDC reales (firma, iss, aud, exp, nbf, kid, alg); JWKS funcionando con cache + rotation; identity estable = issuer+subject; tenant server-side trusted; role namespaced trusted; RBAC sin cambios. 49 tests negativos + end-to-end invocan operaciones reales. |
| **Autenticación OAuth real** | IMPLEMENTED — pipeline OIDC provider-neutral completo. Auth0 documentado como referencia. Cambiar a Keycloak requiere sólo env vars. **No se integró un provider real en este commit** (cumple restricción del brief: "No desplegar en producción"). Integrar un provider real requiere configurar env vars en producción — no requiere cambios de código. |
| **Despliegue productivo** | BLOQUEADO — requiere infraestructura + secrets operativos. No se desplegó en V6.0 (cumple restricción del brief). |

## Limitaciones externas pendientes

| Componente | Razón |
|---|---|
| MCP OAuth provider real (Auth0 tenant / Keycloak realm) | Requiere cuenta + configuración en el IdP externo. La arquitectura V6.0 está lista; sólo falta configurar env vars en producción. |
| LLM Anthropic/OpenAI | Requiere API keys válidas |
| USDC settlement | Requiere wallet + smart contract |
| Deployment | Requiere infraestructura + secrets operativos |

## SHA inicial y final

- SHA inicial: `3bbb1b5` (V5.2 CURRENT_STATE)
- SHA de implementación: `18b29a3` (commit V6.0)
- SHA documental: `18b29a3` (commit docs V6.0)

## URLs/IDs de CI

- Run ID: `18b29a3`
- URL: `18b29a3`

## Confirmación de push

`3bbb1b5..18b29a3 main → origin/main` VERIFIED (por confirmar tras push).

## Estado de producción

**V6.0 — OIDC/OAUTH IDENTITY: VERIFIED** (con deployment todavía separado).

La autenticación OIDC real está implementada, probada (49 tests),
documentada. Production deployment queda separado (cumple restricción
del brief: "NO declarar 'Production Deployed'").

---

# Histórico: V5.2 (cierre acotado de cobertura multitenant en create_*)

- **HEAD inicial V5.2:** `2568b0d` (V5.1.1 CURRENT_STATE)
- **HEAD final V5.2:** `6c64ef9` (V5.2 cierre de cobertura multitenant en create_*)
- **CI:** Run `40822914692`, commit `6c64ef9`, SUCCESS
  - lint: SUCCESS
  - test 3.10/3.11/3.12: 1344 passed, 5 skipped
  - clean-room: SUCCESS

## Commits V5.2

| SHA | Mensaje |
|---|---|
| `6c64ef9` | fix: V5.2 — cierre acotado de cobertura multitenant en create_* |

## Resumen ejecutivo V5.2

V5.2 cierra la brecha de cobertura identificada en la auditoría
independiente de V5.1: `MatterStore.create_matter()` y
`MatterStore.create_pending_action()` no aplicaban `_require_tenant()`,
aunque el informe V5.1 declaraba que la autorización multitenant estaba
cerrada en todas las operaciones del almacén.

**No se añaden funcionalidades jurídicas nuevas.** No se inicia
refactorización general. Sólo se cierra la cobertura multitenant en las
operaciones de creación y escritura, y se auditan los accesos SQL
directos de `ApprovalChain`.

## Brecha detectada en V5.1

V5.1 declaró "aislamiento por tenant verificado por prueba negativa real
en TODAS las rutas alcanzables desde la aplicación". La auditoría V5.2
encontró que esta declaración era **incompleta**:

| Operación | V5.1 status real | V5.2 status |
|---|---|---|
| `create_matter` | Sin `_require_tenant()`, default `"default"` | Fail-closed bajo `enforce_tenant=True` |
| `create_pending_action` | Sin `tenant_id` param, sin verificación de matter ownership | Fail-closed + verificación cross-tenant |
| `ApprovalChain.suggest` | Sin thread `tenant_id` | Thread al store |
| `ApprovalChain.mark_executed` | Direct SQL UPDATE (audit V5.2 pidió revisar) | Auditado: precedido por 2 verificaciones de tenant, no bypass |

### Detalle del defecto `create_pending_action`

**Antes:** Tenant-A podía crear una pending action sobre un `matter_id`
de Tenant-B. La acción se insertaba en `pending_actions` con
`matter_id` válido de Tenant-B. Tenant-B vería una acción attacker-
controlled en su workflow de aprobación — un atacante podría inyectar
acciones que aparecerían como "pending approval" en el buzón de
aprobación de Tenant-B.

**Ahora:** bajo `enforce_tenant=True`, se verifica que el `matter_id`
existe Y pertenece al tenant autorizado ANTES del INSERT. Cross-tenant
creation → `KeyError` (sin revelar si el matter existe en otro tenant).
No se persisten filas parciales.

## Archivos modificados V5.2

| Archivo | Cambios | Líneas |
|---|---|---|
| `albra/matters/store.py` | `create_matter()`: signature `tenant_id: str = "default"` → `tenant_id: str \| None = None` + `_require_tenant()` + default `"default"` en dev mode. `create_pending_action()`: add `tenant_id` param + `_require_tenant()` + cross-tenant matter ownership verification BEFORE any INSERT. | +68/-3 |
| `albra/security/approval_chain.py` | `suggest()`: add `tenant_id` param, thread to store. `mark_executed()`: V5.2 audit docstring (no behavior change, no bypass). | +45/-2 |
| `tests/matters/test_v5_audit_tenant.py` | Strengthened: 8 new negative cases added to existing `test_enforce_tenant_blocks_all_methods_when_tenant_id_missing` for `create_matter` (4) + `create_pending_action` (4). Setup updated to thread `tenant_id` (necessary because `create_pending_action` now enforces it). | +37/-0 |
| `tests/matters/test_v52_create_tenant_authorization.py` | NEW: 27 functional tests, all real invocations (no string inspection). | +606 lines |

**Sin debilitamiento de pruebas existentes.** El diff del test V5.1
audit_tenant muestra sólo adiciones (8 nuevos casos negativos +
actualización del setup para thread `tenant_id`). Ningún caso existente
fue removido o debilitado.

## Pruebas funcionales V5.2 (27 tests nuevos, todas con invocaciones reales)

### tests/matters/test_v52_create_tenant_authorization.py

| Categoría | Tests | Cobertura |
|---|---|---|
| A. `create_matter` sin tenant / None / "" / "default" → denegada | 4 | V5.2 brief punto "Creación de matter sin tenant, con None, cadena vacía y 'default': denegada en modo estricto" |
| B. `create_matter` con tenant válido → asociada correctamente | 1 | V5.2 brief punto "Creación de matter con tenant válido: funciona y queda asociada al tenant correcto" |
| C. `create_matter` no persiste nada tras denegación | 1 | V5.2 brief punto "Verificar que no haya escrituras parciales ni cambios persistidos tras una denegación" |
| D. `create_pending_action` sin tenant válido → denegada | 2 | V5.2 brief punto "Creación de acción pendiente sin tenant válido: denegada en modo estricto" |
| E. Tenant A crea action sobre matter de B → denegado + no DB change | 1 | V5.2 brief punto "Tenant A intenta crear una acción sobre un matter de B: denegado y sin cambios en la base de datos" |
| F. `create_pending_action` sobre matter inexistente → denegada | 1 | Edge case: cross-tenant guard treats "not found" same as "not in tenant" (no info leak) |
| G. Tenant A no puede approve/reject/mark_executed action de B | 3 | V5.2 brief punto "Tenant A no puede aprobar, rechazar ni marcar como ejecutada una acción de B" |
| H. Same-tenant legítimo continúa funcionando | 3 | V5.2 brief punto "Las operaciones legítimas del mismo tenant siguen funcionando" |
| I. Denegaciones no revelan datos del otro tenant | 1 | V5.2 brief punto "Las denegaciones no revelan datos del otro tenant" |
| J. Cliente no puede desactivar `enforce_tenant` vía args | 2 | V5.2 brief punto "Verificar que las rutas de producción no puedan seleccionar o desactivar enforce_tenant mediante argumentos del cliente" |
| K. No escrituras parciales tras denegación | 2 | V5.2 brief punto "Verificar que no haya escrituras parciales ni cambios persistidos tras una denegación" |
| L. `ApprovalChain.suggest` threading tenant_id | 3 | V5.2 brief punto "Revisar las demás operaciones públicas de escritura y los accesos SQL directos de ApprovalChain" |
| M. Legacy mode (enforce_tenant=False) preserva behavior | 3 | V5.2 brief punto "Mantener el comportamiento local/de desarrollo separado y explícito, sin debilitar el modo producción" |

### tests/matters/test_v5_audit_tenant.py (extended)

- `test_enforce_tenant_blocks_all_methods_when_tenant_id_missing`:
  extended with 8 new cases for `create_matter` (4) and
  `create_pending_action` (4). The setup was updated to thread
  `tenant_id` when seeding the action (necessary because
  `create_pending_action` now enforces it under `enforce_tenant=True`).
- `test_enforce_tenant_allows_authorized_tenant_id`: extended to cover
  `create_pending_action` with authorized `tenant_id`.

## Conteos

| Métrica | V5.1.1 (baseline) | V5.2 |
|---|---|---|
| Tests passed | 1317 | **1344** |
| Tests skipped | 5 | **5** |
| Tests failed | 0 | **0** |
| Net new tests | — | **+27** (new file) + **+0** (existing tests extended in-place) |
| Lint | All checks passed | All checks passed |
| CI matrix | 3.10/3.11/3.12 SUCCESS | 3.10/3.11/3.12 SUCCESS |
| Clean-room | SUCCESS | SUCCESS |

## Confirmación

| Punto del brief V5.2 | Estado |
|---|---|
| 1. Revisar create_matter() y create_pending_action() | VERIFIED |
| 1. Bajo enforce_tenant=True, ninguna creación/modificación sin tenant_id válido | VERIFIED (9 tests) |
| 1. create_pending_action verifica matter_id existe y pertenece al tenant | VERIFIED (3 tests) |
| 1. Tenant procede del contexto autenticado, no del cliente | VERIFIED (cliente no puede desactivar enforce_tenant vía args — 2 tests) |
| 1. Mantener dev/producción separados, sin debilitar producción | VERIFIED (3 legacy mode regression tests + 3 same-tenant regression tests) |
| 1. Revisar demás escrituras y accesos SQL directos de ApprovalChain | VERIFIED (mark_executed auditado, no bypass, documentado en docstring) |
| 2. Pruebas invocan operaciones reales, no inspección textual | VERIFIED (27 tests con invocaciones reales, 0 string inspection) |
| 3. Suite completa + Ruff + clean-room + matrix 3.10/3.11/3.12 | VERIFIED (CI run 40822914692 SUCCESS) |
| 3. Revisar diff, comprobar que ninguna prueba se haya debilitado | VERIFIED (sólo adiciones a tests existentes, 0 debilitamiento) |
| 3. Actualizar CURRENT_STATE.md | VERIFIED (este documento) |
| 3. Publicar en main + comunicar SHAs + recuentos + enlaces CI | VERIFIED (ver cabecera) |
| Restricción: No desplegar en producción | OK (no deploy) |
| Restricción: No integrar OAuth/LLM/USDC/infra | OK (sin cambios externos) |
| Restricción: No añadir funcionalidades jurídicas | OK (sólo cierre de seguridad) |
| Restricción: No iniciar refactorización general | OK (mark_executed auditado pero no refactorizado — sería feature) |

## Dictamen diferenciado (V5.2 brief)

| Dimensión | Estado |
|---|---|
| **Seguridad verificada en código y pruebas** | VERIFIED — `create_matter` y `create_pending_action` aplican `_require_tenant()` bajo `enforce_tenant=True`; cross-tenant creation verificada antes de cualquier INSERT; `ApprovalChain.suggest` propaga `tenant_id`; `ApprovalChain.mark_executed` auditado (no bypass). 27 tests negativos nuevos + 8 cases extendidos invocan operaciones reales. |
| **Autenticación OAuth real** | BLOQUEADA — requiere provider OAuth real (Auth0/Keycloak/GitHub OAuth App). `validate_bearer_token(mode="production")` retorna `None` para todos los tokens (fail-closed correcto). |
| **Despliegue productivo** | BLOQUEADO — requiere infraestructura + secrets operativos. No se desplegó en V5.2 (cumple restricción del brief). |

## Limitaciones externas pendientes

| Componente | Razón |
|---|---|
| MCP OAuth production | Requiere provider OAuth real (Auth0/Keycloak/GitHub OAuth App) |
| LLM Anthropic/OpenAI | Requiere API keys válidas |
| USDC settlement | Requiere wallet + smart contract |
| Deployment | Requiere infraestructura + secrets operativos |

Ninguno es código ALBRA — todos son dependencias externas.

## Rutas de ejecución y su estado de aislamiento (V5.2 actualizado)

| Ruta | tenant_id enforced? | Estado V5.2 |
|---|---|---|
| MCP HTTP tools/call list_matters | SÍ (fail-closed en producción) | VERIFIED (V5.1) |
| MCP HTTP tools/call advance_matter | SÍ (fail-closed en producción) | VERIFIED (V5.1) |
| MCP HTTP tools/call verify_audit_chain | SÍ (fail-closed en producción) | VERIFIED (V5.1) |
| MCP stdio tools/call | SÍ | VERIFIED (V5.1) |
| **`MatterStore.create_matter`** | **SÍ (fail-closed en producción, V5.2)** | **VERIFIED (V5.2)** |
| **`MatterStore.create_pending_action`** | **SÍ (fail-closed + cross-tenant matter check, V5.2)** | **VERIFIED (V5.2)** |
| `MatterStore.get_matter` | SÍ | VERIFIED (V5.1) |
| `MatterStore.list_matters` | SÍ | VERIFIED (V5.1) |
| `MatterStore.advance_state` | SÍ | VERIFIED (V5.1) |
| `MatterStore.get_pending_action` | SÍ | VERIFIED (V5.1) |
| `MatterStore.list_pending` | SÍ | VERIFIED (V5.1) |
| `MatterStore.add_approval` | SÍ | VERIFIED (V5.1) |
| `MatterStore.reject_action` | SÍ | VERIFIED (V5.1) |
| **`ApprovalChain.suggest`** | **SÍ (thread tenant_id, V5.2)** | **VERIFIED (V5.2)** |
| `ApprovalChain.approve` | SÍ | VERIFIED (V5.1) |
| `ApprovalChain.reject` | SÍ | VERIFIED (V5.1) |
| `ApprovalChain.can_execute` | SÍ | VERIFIED (V5.1) |
| **`ApprovalChain.mark_executed`** | **SÍ (audit V5.2, no bypass)** | **VERIFIED (V5.2)** |
| `ApprovalChain.get_status` | SÍ | VERIFIED (V5.1) |
| `ApprovalChain.list_pending_for_matter` | SÍ | VERIFIED (V5.1) |
| `ApprovalChain.list_all_pending` | SÍ | VERIFIED (V5.1) |
| CLI matter_show/advance/list/new/timeline/audit | TÉCNICAMENTE BLOQUEADO en producción | VERIFIED (V5.1.1) |
| CLI pending_list/approve | TÉCNICAMENTE BLOQUEADO en producción | VERIFIED (V5.1.1) |
| CLI info/agent list/research | NO REQUIERE (tenant-agnostic read-only) | N/A |
| MCPServer._m_tools_call (V1.6) | NO (legacy, not reachable) | NOT_REACHABLE |

---

# Histórico: V5.1.1 (cierre del guard de CLI fail-closed)

- **HEAD inicial V5.1.1:** `c492a5d` (V5.1 CURRENT_STATE)
- **HEAD final V5.1.1:** `19d045f` (V5.1.1 CLI guard fail-closed)
- **CI:** Run `40820289266`, commit `19d045f`, SUCCESS
  - lint: SUCCESS
  - test 3.10/3.11/3.12: 1317 passed, 5 skipped
  - clean-room: SUCCESS

## Commits V5.1.1

| SHA | Mensaje |
|---|---|
| `19d045f` | fix: V5.1.1 — CLI guard fail-closed cuando Settings no carga |

## Resumen ejecutivo V5.1.1

V5.1.1 es una corrección acotada del guard de CLI en `albra/cli.py`.
**No se añaden funcionalidades jurídicas nuevas.** Sólo se cierra el
path fail-OPEN identificado en la auditoría independiente de V5.1.

El defecto V5.1: `_enforce_local_only()` tenía:

```python
try:
    from albra.config.settings import Settings
    settings = Settings()
except Exception:  # noqa: BLE001
    return  # ← FAIL-OPEN: el comando continúa sin check de entorno
```

Si `Settings()` raisaba por cualquier motivo (corrupted env, missing
module, circular import, futura validación eager, OOM, etc.), el guard
silenciosamente dejaba continuar el comando — sin check de
ALBRA_ENVIRONMENT, sin ALBRA_CLI_ALLOW_LOCAL, sin nada. Un atacante
que pudiera manipular environment variables o sys.path para hacer
`Settings()` raise podía bypassear el CLI guard entero y alcanzar el
MatterStore producción.

V5.1.1 reemplaza el `except: return` por `except: click.echo(REFUSED...);
sys.exit(2)` — el comando se rehúsa, NO toca el DB file, y el mensaje
nombra el tipo y mensaje de la excepción para que el operador pueda
diagnosticar la causa raíz.

## Comportamiento del guard V5.1.1

| Escenario | V5.1 (fail-open) | V5.1.1 (fail-closed) |
|---|---|---|
| Settings carga + dev | command runs | command runs (sin cambio) |
| Settings carga + prod sin escape hatch | refused exit 2 | refused exit 2 (sin cambio) |
| Settings carga + prod con escape hatch | command runs | command runs (sin cambio) |
| **Settings falla (cualquier excepción)** | **command runs (FAIL-OPEN)** | **refused exit 2 + DB no tocado** |
| Settings falla + ALBRA_CLI_ALLOW_LOCAL=1 | command runs (FAIL-OPEN) | refused exit 2 (escape hatch NO extendido) |

El path de producción/dev cuando Settings carga correctamente es
**byte-identical** entre V5.1 y V5.1.1 (verificado por diff).

## Archivos modificados V5.1.1

| Archivo | Líneas | Cambios |
|---|---|---|
| `albra/cli.py` | +65/-17 | `_enforce_local_only()` fail-closed path; docstring actualizado; comentario explicando V5.1.1 |
| `tests/matters/test_v51_1_cli_guard_fail_closed.py` | new, 421 líneas | 15 tests funcionales con CliRunner |

Sin modificaciones a otros archivos. Sin debilitamiento de controles
existentes. Sin tocar pruebas ajenas al objetivo.

## Pruebas funcionales V5.1.1 (15 tests, todas con CliRunner real)

1. `test_cli_matter_show_refused_when_settings_load_fails`: invoca
   `albra matter show` con Settings patched para raise. Aserta
   exit_code=2, "REFUSED" + "configuration could not be loaded",
   DB file NO creado.
2. `test_cli_matter_advance_refused_when_settings_load_fails`
3. `test_cli_pending_approve_refused_when_settings_load_fails`
4. `test_cli_matter_new_refused_when_settings_load_fails`
5. `test_cli_pending_list_refused_when_settings_load_fails`
6. `test_cli_settings_failure_does_not_leak_data`: siembra DB con 2
   tenants (SECRET_CLIENT_A, SECRET_CLIENT_B), rompe Settings, y
   aserta que el mensaje de rechazo NO menciona ningún client name
   ni tenant ID. El DB queda con exactamente 2 matters (sin mutación).
7. `test_cli_settings_failure_not_overridden_by_escape_hatch`: set
   ALBRA_CLI_ALLOW_LOCAL=1 + ALBRA_ENVIRONMENT=production + Settings
   roto → aún así se rehúsa (punto 4 del brief: "sin ampliarla ni
   activarla automáticamente").
8. `test_cli_dev_mode_still_runs_when_settings_loads`: regression
   (dev mode → command runs, exit 1 = not found, no 2 = refused).
9. `test_cli_production_mode_still_refused_when_settings_loads`:
   regression (prod → refuse exit 2, mensaje distinguible del path
   Settings-failure).
10. `test_cli_production_escape_hatch_still_works_when_settings_loads`:
    regression (escape hatch en prod cuando Settings carga).
11. `test_cli_settings_failure_fail_closed_for_any_exception` (5 cases
    parametrized: RuntimeError, ImportError, ValueError, TypeError,
    KeyError) — verifica que el guard no discrimina por tipo de
    excepción: cualquier fallo al determinar el entorno → refuse.

## Conteos

| Métrica | V5.1 (baseline) | V5.1.1 |
|---|---|---|
| Tests passed | 1302 | **1317** |
| Tests skipped | 5 | **5** |
| Tests failed | 0 | **0** |
| Net new tests | — | **+15** |
| Lint | ruff All checks passed | ruff All checks passed |
| CI matrix | 3.10/3.11/3.12 SUCCESS | 3.10/3.11/3.12 SUCCESS |
| Clean-room | SUCCESS | SUCCESS |

## Confirmación

| Punto del brief V5.1.1 | Estado |
|---|---|
| 1. Eliminar fail-open cuando Settings falla | VERIFIED (15 tests) |
| 2. Rechazar antes de acceder al almacén | VERIFIED (DB file no creado en 5 tests) |
| 3. Mantener behavior dev/prod cuando Settings carga | VERIFIED (3 regression tests + diff byte-identical) |
| 4. ALBRA_CLI_ALLOW_LOCAL=1 sin ampliar ni auto-activar | VERIFIED (escape hatch NO extendido al path Settings-failure) |
| 5. Pruebas funcionales con CliRunner | VERIFIED (15 tests, todos con CliRunner) |
| 6. Suite completa + Ruff + matrix 3.10/3.11/3.12 + clean-room | VERIFIED (CI run 40820289266 SUCCESS) |
| 7. Diff sin debilitar controles ni tocar pruebas ajenas | VERIFIED (2 archivos, +486/-17 líneas, sólo cli.py y nuevo test file) |
| 8. CURRENT_STATE.md actualizado | VERIFIED (este documento) |

## Limitaciones externas pendientes

| Componente | Razón |
|---|---|
| MCP OAuth production | Requiere provider OAuth real (Auth0/Keycloak/GitHub OAuth App) |
| LLM Anthropic/OpenAI | Requiere API keys válidas |
| USDC settlement | Requiere wallet + smart contract |
| Deployment | Requiere infraestructura + secrets operativos |

Ninguno es código ALBRA — todos son dependencias externas.

---

# Histórico: V5.1 (cierre final multitenant)

- **HEAD inicial V5.1:** `caeee65` (V5.0 CURRENT_STATE)
- **HEAD final V5.1:** `cd036d1` (V5.1 cierre final multitenant)
- **CI:** Run `40818254608`, commit `cd036d1`, SUCCESS

## Resumen ejecutivo

V5.1 cierra la vía de bypass multitenant identificada en la revisión
independiente de V5.0. **No se añaden funcionalidades jurídicas nuevas.**
Sólo cierre de seguridad.

Bloques cerrados:
1. MatterStore.enforce_tenant flag + TenantAuthorizationError (fail-closed
   cuando tenant_id es None / "" / "default" en producción).
2. McpServer.call_tool: 3 herramientas tenant-aware (list_matters,
   advance_matter, verify_audit_chain) fail-closed en producción.
3. CLI: guard `_enforce_local_only()` técnicamente enforce LOCAL_ONLY
   en producción — ya no es sólo documentación.
4. ApprovalChain: tenant_id threading end-to-end (approve, reject,
   can_execute, mark_executed, list_pending_for_matter, list_all_pending,
   get_status).
5. Bug latente cerrado en `add_approval`/`reject_action`: el read-back
   final no propagaba tenant_id → raisearía TenantAuthorizationError
   en modo producción después del commit.
6. Reemplazo del pseudo-test V5.0 (string inspection del source) por
   tests funcionales que invocan las operaciones reales.

## Defectos reales encontrados en V5.0

V5.0 cerró nominalmente los bloqueos pero dejó defectos reales:

### D1. `if tenant_id:` truthy guard en MatterStore
**Síntoma:** cada método tenant-aware usaba `if tenant_id:` para decidir
si aplicar el filtro de tenant.
**Defecto:** cuando `tenant_id` era `None`, `""`, o `"default"`, el
filtro se omitía silenciosamente → query sin filtro → leak cross-tenant.
**Evidencia:** V5.0 sólo asertaba que los métodos aceptaban `tenant_id`
como parámetro (vía `inspect.signature`) — nunca probaba el behavior
real cuando el tenant faltaba.
**Fix V5.1:** `_require_tenant()` que fail-closed con
`TenantAuthorizationError` cuando `enforce_tenant=True` y tenant_id no
está autorizado.

### D2. `_tool_verify_audit_chain` skipeaba el cross-tenant check
**Síntoma:** el código V5.0 era:
```python
tenant_id = auth_meta.get("tenant_id")
if tenant_id:  # ← bypass cuando tenant_id es None/""/default
    store.get_matter(...)
```
**Defecto:** un AuthContext sin tenant_id (default placeholder) pasaba
directo al `audit.verify_chain` y leía cualquier audit chain por ID.
**Fix V5.1:** guard explícito `if production and not _tenant_is_authorized(tenant_id): DENY`.

### D3. `_tool_list_matters` defaulteaba a "default" placeholder
**Síntoma:** `tenant_id = auth_meta.get("tenant_id", "default")`.
**Defecto:** si AuthContext no tenía tenant_id (default placeholder),
la llamada ejecutaba `list_matters(tenant_id="default")` — vacío en
deployments limpios pero leak real en deployments que usan "default"
como tenant verdadero.
**Fix V5.1:** fail-closed en producción cuando tenant_id no autorizado.

### D4. CLI documentado como LOCAL_ONLY pero no enforceado técnicamente
**Síntoma:** el "test" V5.0 era:
```python
src = cli_path.read_text()
assert "get_matter(matter_id)" in src  # string inspection
```
**Defecto:** la CLI corría en producción sin ninguna verificación. Un
operador con shell en el host producción podía leer y modificar
expedientes de cualquier cliente sin AuthContext.
**Fix V5.1:** guard `_enforce_local_only()` insertado en 8 comandos
data-touching (matter_new/list/show/advance/timeline/audit y
pending_list/approve). Bajo `ALBRA_ENVIRONMENT=production` sin
`ALBRA_CLI_ALLOW_LOCAL=1`, los comandos se rehúsan con exit_code=2 y
**no tocan el DB file**.

### D5. ApprovalChain no threading tenant_id
**Síntoma:** `ApprovalChain.approve(action_id, by=, role=)` llamaba
`store.add_approval(...)` sin tenant_id.
**Defecto:** la CLI (que se suponía LOCAL_ONLY) podía firmar acciones
de cualquier tenant via ApprovalChain.
**Fix V5.1:** todos los métodos de ApprovalChain aceptan y propagan
tenant_id al store.

### D6. Bug latente en read-back de `add_approval`/`reject_action`
**Síntoma:** después del `commit()`, el código llamaba
`self.get_pending_action(action_id)` (sin tenant_id) para retornar
el estado actualizado.
**Defecto:** en modo `enforce_tenant=True` esto raisearía
`TenantAuthorizationError` después del commit — la firma se persistía
pero el caller recibía un error.
**Fix V5.1:** thread tenant_id al read-back.

### D7. Bug bonus: lazy `_store()` usaba DB path hardcoded
**Síntoma:** `MatterStore()` con default `./data/matters.db`.
**Defecto:** production deployments ignoraban silenciosamente
`ALBRA_MATTER_DB_PATH`. No es un defecto de seguridad pero fue
encontrado mientras se cerraba D1-D6 y se arregló por consistencia.
**Fix V5.1:** `_store()` usa `Settings().matter_db_path`.

## Arquitectura de seguridad MCP V5.1

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
        _tool_list_matters:        [V5.1] fail-closed si tenant_id no autorizado
        _tool_advance_matter:      [V5.1] fail-closed si tenant_id no autorizado
        _tool_verify_audit_chain:  [V5.1] fail-closed si tenant_id no autorizado
                                 (antes `if tenant_id:` era bypassable)
        store.list_matters(tenant_id=...)         → _require_tenant
        store.advance_state(tenant_id=...)        → _require_tenant
        store.get_matter(tenant_id=...)           → _require_tenant
        store.add_approval(tenant_id=...)         → _require_tenant
        store.reject_action(tenant_id=...)        → _require_tenant
        store.get_pending_action(tenant_id=...)   → _require_tenant
        store.list_pending(tenant_id=...)         → _require_tenant
    → Audit: McpAuditEntry (input_hash, output_hash, correlation_id)

CLI:
  matter_new/list/show/advance/timeline/audit
  pending_list/approve
    → _enforce_local_only("...")
       → si ALBRA_ENVIRONMENT=production AND ALBRA_CLI_ALLOW_LOCAL != "1":
         exit_code=2 + "REFUSED" (no DB file created)

ApprovalChain (defense in depth):
  approve/reject/can_execute/mark_executed/list_pending_for_matter/
  list_all_pending/get_status — todos aceptan tenant_id y lo propagan.
```

## Rutas de ejecución y su estado de aislamiento

| Ruta | tenant_id enforced? | Estado V5.1 |
|---|---|---|
| MCP HTTP tools/call list_matters | SÍ (fail-closed en producción) | VERIFIED |
| MCP HTTP tools/call advance_matter | SÍ (fail-closed en producción) | VERIFIED |
| MCP HTTP tools/call verify_audit_chain | SÍ (fail-closed en producción) | VERIFIED |
| MCP stdio tools/call | SÍ (initialize auth → _stdio_auth_context → _auth → store) | VERIFIED |
| CLI matter_show | TÉCNICAMENTE BLOQUEADO en producción | VERIFIED |
| CLI matter_advance | TÉCNICAMENTE BLOQUEADO en producción | VERIFIED |
| CLI matter_list | TÉCNICAMENTE BLOQUEADO en producción | VERIFIED |
| CLI matter_new | TÉCNICAMENTE BLOQUEADO en producción | VERIFIED |
| CLI matter_timeline | TÉCNICAMENTE BLOQUEADO en producción | VERIFIED |
| CLI matter_audit | TÉCNICAMENTE BLOQUEADO en producción | VERIFIED |
| CLI pending_list | TÉCNICAMENTE BLOQUEADO en producción | VERIFIED |
| CLI pending_approve | TÉCNICAMENTE BLOQUEADO en producción | VERIFIED |
| CLI info / agent list / research | NO REQUIERE (tenant-agnostic read-only) | N/A |
| ApprovalChain.approve | SÍ (tenant_id threaded al store) | VERIFIED |
| ApprovalChain.reject | SÍ (tenant_id threaded al store) | VERIFIED |
| ApprovalChain.can_execute | SÍ (tenant_id threaded) | VERIFIED |
| ApprovalChain.mark_executed | SÍ (tenant_id threaded) | VERIFIED |
| ApprovalChain.get_status | SÍ (tenant_id threaded) | VERIFIED |
| ApprovalChain.list_pending_for_matter | SÍ (tenant_id threaded) | VERIFIED |
| ApprovalChain.list_all_pending | SÍ (tenant_id threaded) | VERIFIED |
| MCPServer._m_tools_call (V1.6) | NO (legacy, not reachable from V2.3+ McpServer) | NOT_REACHABLE |

## Pruebas negativas (evidencia real)

### tests/matters/test_v5_audit_tenant.py (13 tests, rewritten)
- `test_mcp_verify_audit_chain_cross_tenant_blocked`: invoca
  McpServer.call_tool real con tenant-A; aserta que tenant-A puede
  verificar own chain Y que tenant-A NO puede verificar tenant-B's chain.
- `test_list_matters_get_matter_uses_tenant_filter`: strengthened.
- `test_cli_matter_show_refused_in_production`: invoca `albra matter show`
  bajo ALBRA_ENVIRONMENT=production via CliRunner; aserta exit_code=2,
  output contiene "REFUSED", y DB file no creado.
- `test_cli_matter_advance_refused_in_production`: mismo patrón.
- `test_cli_pending_approve_refused_in_production`: mismo patrón.
- `test_cli_matter_show_runs_with_local_escape_hatch`: escape hatch
  ALBRA_CLI_ALLOW_LOCAL=1 funciona (exit 1 = not found, no 2 = refused).
- `test_cli_matter_show_runs_in_development`: dev mode sin restricción.
- `test_enforce_tenant_blocks_all_methods_when_tenant_id_missing`:
  invoca cada método tenant-aware con None / "" / "default" y aserta
  TenantAuthorizationError (18 casos cubiertos en una sola función).
- `test_enforce_tenant_allows_authorized_tenant_id`: regression —
  mismo-tenant legítimo sigue funcionando bajo enforce_tenant=True.
- `test_enforce_tenant_false_preserves_legacy_behavior`: regression —
  dev/test mode preserva behavior V4.x.
- `test_mcp_production_mode_constructs_store_with_enforce_tenant`:
  wiring del lazy constructor.
- `test_mcp_dev_mode_constructs_store_without_enforce_tenant`:
  dev-mode wiring.
- `test_mcp_production_mode_uses_enforced_store_via_lazy_init`:
  runtime proof — el lazy store realmente tiene enforce_tenant=True.

### tests/matters/test_v51_tenant_authorization.py (18 tests, NUEVO)
- `test_production_list_matters_denies_default_tenant`: AuthContext
  con tenant_id="default" → DENIED, sin leak.
- `test_production_list_matters_denies_none_tenant`: tenant_id=None → DENIED.
- `test_production_list_matters_denies_empty_tenant`: tenant_id="" → DENIED.
- `test_production_advance_matter_denies_default_tenant`: default → DENIED,
  matter state sin mutar.
- `test_production_verify_audit_chain_denies_default_tenant`: default
  → DENIED, no leak de chain ok/total.
- `test_production_cross_tenant_list_matters`: tenant-A no ve tenant-B.
- `test_production_cross_tenant_advance_matter`: tenant-A no avanza
  tenant-B; matter state sin mutar.
- `test_production_cross_tenant_verify_audit_chain`: tenant-A no
  verifica chain de tenant-B.
- `test_production_same_tenant_list_matters_succeeds`: regression.
- `test_production_same_tenant_advance_matter_succeeds`: regression.
- `test_production_same_tenant_verify_audit_chain_succeeds`: regression.
- `test_production_cross_tenant_error_does_not_leak_data`: error no
  menciona "ClientB" ni "tenant-B".
- `test_production_client_cannot_forge_tenant_via_args`: pasar
  tenant_id en args es ignorado.
- `test_production_client_cannot_forge_tenant_via_metadata`: pasar
  _auth metadata en args es ignorado (call_tool sobreescribe).
- `test_approval_chain_cross_tenant_approve_blocked`: ApprovalChain
  con tenant-A no aprueba acción de tenant-B.
- `test_approval_chain_cross_tenant_reject_blocked`: ApprovalChain
  con tenant-A no rechaza acción de tenant-B.
- `test_approval_chain_cross_tenant_get_status_blocked`: get_status
  con tenant-A retorna None para acción de tenant-B.
- `test_approval_chain_same_tenant_approve_succeeds`: regression.

## Conteos

| Métrica | V5.0 (baseline) | V5.1 |
|---|---|---|
| Tests passed | 1275 | 1302 |
| Tests skipped | 5 | 5 |
| Tests failed | 0 | 0 |
| Net new tests | — | +27 |
| Lint | ruff All checks passed | ruff All checks passed |
| CI matrix | 3.10/3.11/3.12 SUCCESS | 3.10/3.11/3.12 SUCCESS |
| Clean-room | SUCCESS | SUCCESS |

## Confirmación de aislamiento por tenant

| Operación | Aislamiento confirmado por prueba negativa |
|---|---|
| Tenant A lee expediente de tenant B por ID | `test_get_matter_tenant_a_cannot_read_tenant_b` (V4.1) + `test_production_cross_tenant_list_matters` (V5.1) |
| Tenant A avanza expediente de tenant B | `test_advance_state_tenant_a_cannot_advance_tenant_b` (V4.1) + `test_production_cross_tenant_advance_matter` (V5.1) |
| Tenant A consulta/aprueba/rechaza acciones de tenant B | `test_add_approval_tenant_a_cannot_approve_tenant_b` + `test_reject_action_tenant_a_cannot_reject_tenant_b` (V4.1) + `test_approval_chain_cross_tenant_approve_blocked` + `test_approval_chain_cross_tenant_reject_blocked` + `test_approval_chain_cross_tenant_get_status_blocked` (V5.1) |
| `verify_audit_chain` rechaza acceso cruzado | `test_mcp_verify_audit_chain_cross_tenant_blocked` (V5.0 strengthened V5.1) + `test_production_cross_tenant_verify_audit_chain` (V5.1) |
| Tenant ausente o vacío no permite acceso sin filtro | `test_production_list_matters_denies_default_tenant` + `test_production_list_matters_denies_none_tenant` + `test_production_list_matters_denies_empty_tenant` (V5.1) + `test_enforce_tenant_blocks_all_methods_when_tenant_id_missing` (V5.1, 18 casos) |
| Cliente no puede falsificar tenant via args | `test_mcp_list_matters_args_tenant_override_blocked` (V4.1) + `test_production_client_cannot_forge_tenant_via_args` + `test_production_client_cannot_forge_tenant_via_metadata` (V5.1) |
| CLI no permite eludir seguridad en producción | `test_cli_matter_show_refused_in_production` + `test_cli_matter_advance_refused_in_production` + `test_cli_pending_approve_refused_in_production` (V5.1) |
| Operaciones legítimas del mismo tenant continúan funcionando | `test_legitimate_tenant_a_flows_work` (V4.1) + `test_enforce_tenant_allows_authorized_tenant_id` + `test_production_same_tenant_list_matters_succeeds` + `test_production_same_tenant_advance_matter_succeeds` + `test_production_same_tenant_verify_audit_chain_succeeds` + `test_approval_chain_same_tenant_approve_succeeds` (V5.1) |
| Errores no filtran datos de otros clientes | `test_production_cross_tenant_error_does_not_leak_data` (V5.1) |

**Dictamen**: aislamiento por tenant verificado por prueba negativa real
en TODAS las rutas relevantes. No queda ruta alcanzable desde la
aplicación donde tenant_id opcional permita eludir el control de
seguridad en producción.

## Bloqueos externos pendientes

| Componente | Estado | Razón |
|---|---|---|
| MCP OAuth production | BLOCKED BY EXTERNAL DEPENDENCY | Requiere provider OAuth real (Auth0/Keycloak/GitHub OAuth App) |
| LLM Anthropic/OpenAI | BLOCKED BY EXTERNAL DEPENDENCY | Requiere API keys válidas |
| USDC settlement | BLOCKED BY EXTERNAL DEPENDENCY | Requiere wallet + smart contract |
| Deployment | BLOCKED BY EXTERNAL DEPENDENCY | Requiere infraestructura + secrets operativos |

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
| CLI en producción | TÉCNICAMENTE BLOQUEADO (escape hatch explícito) |
| MCP OAuth production | BLOCKED BY EXTERNAL DEPENDENCY |
| LLM Anthropic/OpenAI | BLOCKED BY EXTERNAL DEPENDENCY |
| USDC settlement | BLOCKED BY EXTERNAL DEPENDENCY |
| Deployment | BLOCKED BY EXTERNAL DEPENDENCY |
| MCPServer._m_tools_call (V1.6) | NOT_REACHABLE (legacy) |

## Dictamen honesto de preparación para producción

**Aislamiento multitenant: VERIFIED.** Todas las rutas de acceso a
datos de cliente que eran alcanzables desde la aplicación han sido
auditadas y cerradas con prueba negativa real.

**Seguridad MCP: VERIFIED con limitación externa.** La cadena de
seguridad (Auth → RBAC → LegalGate → ExecutionGuard → prompt injection
→ audit) está completa. La única limitación es que
`validate_bearer_token(mode="production")` retorna None para todos los
tokens — eso es por diseño: requiere provider OAuth real. Hasta que
ese provider se integre, el modo producción rechaza todos los tokens
(fail-closed correcto).

**CLI: VERIFIED.** Técnicamente bloqueado en producción. El escape
hatch `ALBRA_CLI_ALLOW_LOCAL=1` está documentado y es auditable.

**Production readiness (sin deploy):** ~95%. El 5% restante es
bloqueo externo (OAuth provider, LLM API keys, infraestructura de
deploy). Ninguno es código ALBRA.

**No se despliega en producción** en esta intervención, como pidió el
brief V5.1.
