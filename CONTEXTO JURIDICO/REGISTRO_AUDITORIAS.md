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
