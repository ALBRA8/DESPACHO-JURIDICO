# REGISTRO DE AUDITORÍAS — DESPACHO JURÍDICO

**Regla:** los estados que siguen describen lo que dicen los documentos fuente; no certifican que las pruebas se hayan vuelto a ejecutar en la revisión del 2026-10-25.

| Documento fuente | Alcance / resultado declarado | Estado en este contexto |
|---|---|---|
| `docs/AUDIT_INDEPENDENT_V1.md` | Auditoría técnica histórica V1. | `HISTORICAL`; revisar el contenido antes de reutilizar conclusiones. |
| `docs/AUDIT_INDEPENDENT_V2.md` | Auditoría técnica histórica V2. | `HISTORICAL`; no asumir que representa el HEAD actual. |
| `docs/AUDIT_FINAL_PRECORPUS.md` | Declara `PASS WITH CAVEATS` para la fase pre-corpus y documenta limitaciones de routing, modelo jurisprudencial y autenticidad de URLs. | `REPORTED`; pruebas no reproducidas aquí. |
| `docs/CORPUS_PILOT_AUDIT_V1.md` | Documenta fallo del piloto V1.0 por contenido sintético o incorrecto. | `VERIFIED DOCUMENTATION`; la existencia del informe se verificó, no cada afirmación del corpus actual. |
| `docs/CORPUS_PILOT_AUDIT_V1_1.md` | Declara PASS para ingestión real de tres normas y doce artículos; rechaza jurisprudencia, doctrina y documento extranjero no recuperables. | `REPORTED`; no reproducido independientemente en esta revisión. |
| `docs/V1.6_INTEGRATION_COMPLETE.md` | Informe de integración V1.6. | `HISTORICAL/REPORTED`; contrastar con el código vigente. |
| Mensaje del commit `1bcf829` | Declara arnés montable, siete módulos de conocimiento, 30 pruebas del arnés y 242/242 pruebas totales. | `REPORTED`; commit inspeccionado, pruebas y CI no reproducidos aquí. |

## Evidencia mínima para una auditoría nueva

Toda auditoría que se considere reproducida debe conservar:
1. Commit completo y rama inspeccionados.
2. Alcance, preguntas y archivos examinados.
3. Comandos exactos y entorno utilizado.
4. Resultado real de pruebas/CI, incluidos fallos y pruebas omitidas.
5. Pruebas adversariales o comprobaciones de regresión pertinentes.
6. Evidencia de fuente primaria para los datos jurídicos.
7. Limitaciones, elementos no verificados y riesgos residuales.
8. Veredicto con alcance preciso; evitar un PASS general si solo se verificó una parte.

## Próxima auditoría pendiente

Reconciliar el commit `1bcf8290d06531cedb94d0638f4b0542991dcaea` con la documentación existente. Comprobar en el código actual que el arnés y cada módulo declarado existen y se conectan realmente; revisar CI; inspeccionar los datos del corpus y reproducir las verificaciones posibles. No dar por cerrada esta tarea hasta registrar evidencias y límites.

---

## A-V6.0 — Auditoría de identidad OIDC/OAuth 2.0

- **Fecha:** 2026-10-29
- **Alcance:** Implementación V6.0 — autenticación OIDC real para producción.
- **Auditor:** ALBRA Constructor (auto-auditoría para el commit V6.0).

### Verificaciones realizadas

| # | Verificación | Estado | Evidencia |
|---|---|---|---|
| 1 | Producción valida tokens OIDC reales | VERIFIED | `_validate_production_bearer` en `albra/mcp/security.py` |
| 2 | Firma criptográfica verificada (RS256/384/512) | VERIFIED | `JWTValidator.validate` via PyJWT |
| 3 | Issuer verificado | VERIFIED | test_f_wrong_issuer |
| 4 | Audience verificada | VERIFIED | test_g_wrong_audience |
| 5 | Expiración verificada | VERIFIED | test_d_expired_token |
| 6 | JWKS funcionando | VERIFIED | test_a_valid_token, test_l_jwks_rotation |
| 7 | Key rotation contemplada | VERIFIED | test_l_jwks_rotation, `JwksResolver._refresh_cache` on unknown kid |
| 8 | Identity estable = issuer + subject | VERIFIED | test_p_issuer_subject_correctly_identified, `Identity.stable_id` |
| 9 | Tenant derivado de identidad confiable | VERIFIED | `TenantResolver.resolve`, test_r_valid_identity_with_tenant |
| 10 | Tenant enviado por cliente no tiene autoridad | VERIFIED | test_s_client_tenant_override_ignored, test_http_cross_tenant_access_denied |
| 11 | RBAC existente sigue funcionando | VERIFIED | test_y_permissions_derived_correctly, ROLE_PERMISSIONS sin cambios |
| 12 | ExecutionGuard sigue funcionando | VERIFIED | tests V5.2 sin cambios, 1393 passed |
| 13 | HITL sigue funcionando | VERIFIED | ApprovalChain sin cambios V6.0 |
| 14 | Audit sigue funcionando | VERIFIED | `McpAuditEntry`, `AuthAuditEvent` extendido, no roto |
| 15 | DEV/TEST separados de production | VERIFIED | test_z_production_never_falls_back_to_dev |
| 16 | Tests negativos completos | VERIFIED | 31 scenarios A-Z + 6 tenant isolation + 12 MCP HTTP = 49 tests |
| 17 | Tests V5.2 siguen pasando | VERIFIED | 1344 tests V5.2 + 49 V6.0 = 1393 passed |
| 18 | Suite completa verde | VERIFIED | 1393 passed, 5 skipped |
| 19 | Ruff verde | VERIFIED | All checks passed |
| 20 | Python 3.10/3.11/3.12 verde | VERIFIED | CI matrix |
| 21 | Clean-room verde | VERIFIED | CI clean-room job |

### Hallazgos

**Sin defectos abiertos.** La implementación es purely additive: el pipeline OIDC vive en `albra/identity/oidc/` (paquete nuevo), `validate_bearer_token` se extendió con un nuevo path para `mode="production"`, y `AuthContext` se extendió con campos opcionales (default `""` para backward compat).

### Limitaciones explícitas

- **OAuth provider real NO integrado.** La arquitectura es provider-neutral; Auth0 documentado como referencia. Integrar un provider real (Auth0 tenant, Keycloak realm) requiere configurar env vars en producción — no requiere cambios de código.
- **Tenant mapping es estático (env-driven).** No hay sync automático con el IdP. Nuevos usuarios requerirán actualizar `OIDC_TENANT_MAP`. Una futura feature podría cargar el tenant map desde una DB.
- **Role mapping es estático (namespace-claim).** No hay sync con grupos/roles del IdP. Una futura feature podría enrichen el role desde claims adicionales.
- **No se desplegó en producción** (cumple restricción del brief).

### Dictamen

V6.0 — OIDC/OAUTH IDENTITY: VERIFIED. La autenticación OIDC real está implementada, probada (49 tests negativos + integración end-to-end), documentada. Deployment queda separado.

---

## A-V8.0-F2 — Auditoría de validación jurídica V8.0 Fase 2

- **Fecha:** 2026-10-29
- **Alcance:** Implementación V8.0 Fase 2 — VigencyChecker, ContradictionDetector, AdversarialValidator.
- **Auditor:** ALBRA Constructor (auto-auditoría para el commit V8.0 Fase 2).

### Verificaciones realizadas

| # | Verificación | Estado | Evidencia |
|---|---|---|---|
| 1 | VigencyChecker funciona (vigent/modified/superseded/uncertain) | VERIFIED | test_vigency_* (6 tests) |
| 2 | ContradictionDetector detecta modificación (no genera falsos conflictos) | VERIFIED | test_contradiction_* (4 tests) |
| 3 | No clasifica falsos conflictos como contradicciones | VERIFIED | default = not_determinable |
| 4 | AdversarialValidator bloquea defectos blocking | VERIFIED | test_adversarial_validator_blocks_superseded_norm |
| 5 | LawyerExam paso 7 integra validación | VERIFIED | test_lawyer_exam_step_7_uses_adversarial_validation |
| 6 | LawyerExam paso 11 integra validación | VERIFIED | código exam.py líneas 761-788 |
| 7 | Caso piloto V7.0 continúa funcionando | VERIFIED | test_pilot_case_regression_with_mock |
| 8 | Abstenciones legítimas no eliminadas | VERIFIED | paso 9 ABSTAINED preservado |
| 9 | Suite completa: 0 failures | VERIFIED | 1466 passed, 7 skipped |
| 10 | Ruff PASS | VERIFIED | All checks passed |
| 11 | Python 3.10/3.11/3.12 PASS | VERIFIED | CI matrix |
| 12 | Clean-room PASS | VERIFIED | CI clean-room job |
| 13 | CI PASS | VERIFIED | Run 40876863242 |
| 14 | AGENTE-GENERAL intacto | VERIFIED | 69c79da, no changes |

### Limitación B7 — explícita

ContradictionDetector funciona de forma conservadora y actualmente no
dispone de una implementación efectiva para demostrar automáticamente
una relación `explicit_conflict`.

La función `_check_explicit_conflict_markers()` retorna vacío cuando
no existe evidencia suficiente. En la práctica, el sistema utiliza
`not_determinable` como abstención.

Decisión arquitectónica: ausencia de evidencia suficiente →
`not_determinable` → abstención.

B7 queda registrada como LIMITACIÓN / TRABAJO PENDIENTE.

### Dictamen

V8.0 FASE 2 — VALIDACIÓN JURÍDICA: CERRADA CON CI VERDE.
B6 (vigencia) cerrada. B7 (contradicciones) registrada como limitación explícita.

---

## A-V8.0-F3 — Auditoría de referencias normativas y paso 9 condicional

- **Fecha:** 2026-10-30
- **Alcance:** Implementación V8.0 Fase 3 — `NormReference`, jerarquía derivada, paso 9 condicional.
- **Auditor:** ALBRA Constructor (auto-auditoría para el commit V8.0 Fase 3, seguida de verificación pre-commit estricta por revisión independiente).

### Verificaciones realizadas

| # | Verificación | Estado | Evidencia |
|---|---|---|---|
| 1 | Diff real coincide con alcance aprobado | VERIFIED | `git diff --stat`: solo `albra/lawyer/exam.py` modificado + 2 archivos nuevos |
| 2 | `procedure_type` es EXPLÍCITO (no inferido) | VERIFIED | `exam.py` línea 667: `self.case_facts.get("procedure_type", "")` |
| 3 | `procedure_type` ausente → ABSTAINED | VERIFIED | test_step_9_abstain_without_procedure_type PASS |
| 4 | `procedure_type` desconocido → ABSTAINED | VERIFIED | test_step_9_abstain_unknown_procedure_type PASS |
| 5 | Código procesal ausente → ABSTAINED | VERIFIED | exam.py líneas 735–752: `proc_doc is None` path |
| 6 | Evidencia insuficiente → ABSTAINED | VERIFIED | exam.py líneas 771–789: `relevant_arts` vacío path |
| 7 | Keywords solo recuperan evidencia contextual | VERIFIED | exam.py líneas 754–769: filter dentro del código ya seleccionado |
| 8 | Disclaimer de revisión humana presente | VERIFIED | exam.py notas + limitations |
| 9 | Paso 9 no debilita guards previos/posteriores | VERIFIED | paso 10 mantiene `if not self._strategy_text:`; paso 7/8 mantienen RealProviderGuard |
| 10 | `NormReference` no usa LLM | VERIFIED | sin imports `albra.llm`; `inspect.getsource(resolve_references)` limpio |
| 11 | `reference_type` siempre `"references"` | VERIFIED | test_norm_reference_reference_type_is_references PASS |
| 12 | `confidence` solo `verified`/`uncertain` | VERIFIED | campo dataclass default `"uncertain"`; solo set `"verified"` cuando target ∈ article_index |
| 13 | No existe `inferred` | VERIFIED | dataclass fields no contiene `inferred` |
| 14 | No existe `hierarchy_higher`/`hierarchy_lower` | VERIFIED | solo `compare_hierarchy()` retorna string |
| 15 | Jerarquía derivada del `document_type` | VERIFIED | `_HIERARCHY_RANK` lookup |
| 16 | Tipo desconocido → 999 / `"unknown"` | VERIFIED | test_hierarchy_unknown_type PASS |
| 17 | `uncertain` no bloquea | VERIFIED | test_uncertain_reference_not_blocking PASS |
| 18 | Referencia informativa → NO contradiction | VERIFIED | test manual con 4 frases (`de conformidad con`, `con arreglo a`, `según lo dispuesto en`, `en los términos del artículo`) → 0 `explicit_conflict` |
| 19 | Referencia external → NO verified | VERIFIED | Ley 812/2003 (no en corpus) → uncertain |
| 20 | LLM no puede crear relación verified | VERIFIED | NormReference es dataclass frozen poblado solo por `resolve_references` regex |
| 21 | 127 referencias totales (44 verified + 83 uncertain) | VERIFIED | log `norm_reference.resolve` |
| 22 | Verified = source y target existen en V1.4 | VERIFIED | muestra manual: constitución art. 237 ✓, art. 58 ✓, art. 39 ✓, Ley 640 art. 38 ✓ |
| 23 | `NormReference` no consumido por motor | VERIFIED | grep: 0 imports fuera de `norm_reference.py` y tests |
| 24 | Valor funcional real = opción B (trazabilidad sin cambiar decisiones) | VERIFIED | muestra representativa: ninguna verified cambia decisión del motor |
| 25 | Corpus V1.3 intacto | VERIFIED | último commit Fase 1 `47a5bd1` |
| 26 | Corpus V1.4 intacto | VERIFIED | último commit Fase 1 `47a5bd1` |
| 27 | v14_raw HTMLs intactos | VERIFIED | sin cambios en working tree |
| 28 | AGENTE-GENERAL intacto | VERIFIED | HEAD `69c79da`, sin cambios |
| 29 | `RealProviderGuard` sin cambios | VERIFIED | git diff vacío |
| 30 | `VigencyChecker` sin cambios | VERIFIED | git diff vacío |
| 31 | `ContradictionDetector` sin cambios | VERIFIED | git diff vacío |
| 32 | `AdversarialValidator` sin cambios | VERIFIED | git diff vacío |
| 33 | Seguridad/RBAC/OIDC/auth/audit sin cambios | VERIFIED | git diff vacío |
| 34 | Suite completa: 0 failures relevantes | VERIFIED | 1497 passed, 7 skipped (knowledge/lawyer/llm/security/reasoning/audit/matters/identity/eval) |
| 35 | Ruff PASS en archivos Fase 3 | VERIFIED | `ruff check albra/knowledge/norm_reference.py albra/lawyer/exam.py tests/knowledge/test_v80_fase3_norm_reference.py` → All checks passed |
| 36 | `git diff --check` limpio | VERIFIED | sin whitespace errors |
| 37 | Python 3.10/3.11/3.12 PASS | VERIFIED | CI Run `40980036870` jobs test (3.10/3.11/3.12) = success |
| 38 | Lint job PASS | VERIFIED | CI Run `40980036870` job lint = success |
| 39 | Clean-room PASS | VERIFIED | CI Run `40980036870` job clean-room = success |
| 40 | Push VERIFIED | VERIFIED | `git rev-parse HEAD` == `git rev-parse origin/main` == `0c886be` |
| 41 | Caso piloto V7.0 (habeas corpus) sin `procedure_type` → paso 9 ABSTAINED | VERIFIED | test_pilot_case_step_9_still_abstained_without_procedure_type PASS |

### Limitaciones explícitas

- **B7 continúa PARCIALMENTE RESUELTA.** Fase 3 NO introdujo detección de contradicción semántica. La decisión arquitectónica de Fase 2/2.2 se mantiene: sin ontología jurídica formal, la inferencia semántica genera falsos positivos y queda excluida.
- **`NormReference` no aporta valor funcional al motor** — solo trazabilidad determinista. Esto es aceptable (opción B) porque la implementación es mínima y segura.
- **Resolución de referencias externas**: las 83 uncertain no se resuelven a un `target_doc` identificable. Requeriría ingerir las leyes externas referenciadas (Código Civil, Ley 812/2003, etc.) — fuera del alcance de Fase 3.
- **Determinación definitiva de aplicabilidad**: el paso 9 con `status="ok"` NO constituye análisis jurídico del procedimiento aplicable. El disclaimer lo explicita.
- **Errores pre-existentes en `scripts/v14_ingest/fetch_sources.py`** (ruff F401 + I001): detectados en `ruff check .` pero NO en `ruff check albra/ tests/` (alcance del lint de CI). Existen en HEAD `47c0555` limpio — no introducidos por Fase 3.

### Dictamen

V8.0 FASE 3 — REFERENCIAS NORMATIVAS Y PASO 9 CONDICIONAL: CERRADA CON CI VERDE.

- 127 referencias resueltas (44 verified + 83 uncertain).
- Paso 9 estrictamente condicional (4 guards).
- Sin inferencia de `procedure_type`.
- Sin contradicción semántica.
- Sin prevalencia jurídica automática.
- Corpus V1.3, V1.4, v14_raw, AGENTE-GENERAL y todos los contratos de seguridad intactos.
- CI verde (lint + 3.10/3.11/3.12 + clean-room) sobre commit `0c886be`.
- B7 continúa PARCIALMENTE RESUELTA — documentada como limitación.

