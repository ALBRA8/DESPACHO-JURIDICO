# REGISTRO DE DECISIONES — CONTEXTO JURÍDICO

Este registro diferencia decisiones explícitas de propuestas e informes. Una decisión solo puede marcarse como aprobada si existe aprobación real.

## DJ-001 — Crear memoria documental dentro del repositorio jurídico

- **Estado:** `APPROVED`
- **Fecha:** 2026-10-25
- **Decisión:** crear `CONTEXTO JURIDICO/` dentro de `ALBRA8/DESPACHO-JURIDICO`.
- **Motivo:** preservar continuidad entre sesiones, reunir el estado actual, registrar decisiones y auditorías y documentar aprendizajes.
- **Alcance:** documentación. No autoriza por sí misma cambios al código jurídico ni a la arquitectura.
- **Criterio de cierre:** carpeta con punto de entrada, estado actual, índice, decisiones, auditorías y estado del corpus.

## DJ-002 — Mantener el ADN universal separado del conocimiento jurídico

- **Estado:** `APPROVED` como principio rector del proyecto, documentado en el README del repositorio.
- **Decisión:** mantener separadas las capacidades transversales del agente y los datos especializados del dominio jurídico.
- **Consecuencia:** una fuente jurídica, una regla legal o un procedimiento de litigio no debe presentarse como parte del ADN universal por el solo hecho de ser útil para el Despacho.

## DJ-003 — No presentar conocimiento sintético como fuente jurídica real

- **Estado:** `APPROVED` como regla de calidad y seguridad del proyecto.
- **Motivo:** la auditoría del corpus V1.0 documentó normas, artículos, jurisprudencia y doctrina sintéticos o mal identificados.
- **Consecuencia:** los elementos sin fuente/contenido verificable se rechazan, se mantienen fuera del corpus activo o se marcan expresamente como no verificados.

## DJ-004 — Usar el Despacho terminado como guía para un futuro agente contador

- **Estado:** `PROPOSED`
- **Fecha:** 2026-10-25
- **Intención:** aprovechar la documentación final del proyecto jurídico como referencia para diseñar un agente especializado en contabilidad.
- **Límite:** no copiar conocimiento jurídico al dominio contable, no asumir requisitos contables no investigados y no iniciar la construcción del contador dentro de este proyecto.
- **Siguiente paso para aprobar:** terminar la reconciliación y auditoría del Despacho, identificar qué elementos son ADN universal y qué elementos son exclusivamente jurídicos, y redactar una especificación separada del contador.

## Regla para nuevas entradas

Cada decisión futura debe incluir identificador, fecha, estado, contexto, decisión, alternativas relevantes, consecuencias, evidencia o enlaces, y condiciones para revisarla. Registrar una propuesta como `PROPOSED`; no convertirla en `APPROVED` por repetición.

---

## D-V6.0 — Identidad OIDC/OAuth 2.0 real para producción

- **Identificador:** D-V6.0
- **Fecha:** 2026-10-29
- **Estado:** APPROVED
- **Contexto:** Hasta V5.2, `validate_bearer_token(mode="production")` retornaba `None` para todo token — fail-closed correcto pero sin autenticación real. La auditoría independiente pidió implementar OIDC/OAuth 2.0 real.

- **Decisión:** Implementar una abstracción OIDC **provider-neutral** en `albra/identity/oidc/`. Auth0 como proveedor de referencia documentado; la arquitectura permite cambiar a Keycloak u otro OIDC-compatible sin tocar MatterStore/RBAC/ExecutionGuard/HITL/audit.

- **Pipeline (7 etapas):**
  1. Bearer token (JWT) extraído del header Authorization.
  2. `JWTValidator` valida firma criptográfica (RS256/384/512) vía JWKS, algoritmo permitido, kid presente, iss, aud, exp, nbf, iat.
  3. `Identity` construida con `(issuer, subject)` como raíz de seguridad. `stable_id` = SHA-256(issuer||subject). Email NUNCA es raíz de identidad.
  4. `TenantResolver` resuelve el tenant desde un mapa **server-side trusted** (`OIDC_TENANT_MAP` o `OIDC_TENANT_MAP_PATH`). El `tenant_id` enviado por el cliente NO tiene autoridad.
  5. `RoleResolver` mapea el identity a un role ALBRA (paralegal/abogado/socio/cliente/admin) desde un claim **namespaced trusted** (`https://albra.dev/role` por defecto). Un claim `role` "bare" (sin namespace) NUNCA se acepta.
  6. `build_auth_context_from_oidc` construye `AuthContext` con `auth_method="oidc"`, `issuer`, `subject`, `tenant_id`, `role`, `permissions` desde `ROLE_PERMISSIONS`.
  7. RBAC → ExecutionGuard → MatterStore (con `enforce_tenant=True`) → audit.

- **Alternativas consideradas:**
  - *Acoplar a Auth0 SDK nativo* — RECHAZADO: amarraría el dominio a un proveedor.
  - *Implementar criptografía JWT manualmente* — RECHAZADO: re-inventar PyJWT/cryptography es peligroso.
  - *Aceptar `sub` como identity global* — RECHAZADO: dos issuers pueden asignar el mismo `sub`.
  - *Aceptar `email` como raíz de identidad* — RECHAZADO: el email es metadata, no autoridad.
  - *Aceptar `role` claim "bare"* — RECHAZADO: atacante que controle otro IdP podría mint un `role: "admin"`.
  - *Aceptar `tenant_id` del cliente* — RECHAZADO: permite escalación cross-tenant.

- **Consecuencias:**
  - Producción requiere `OIDC_ISSUER`, `OIDC_AUDIENCE`, y `OIDC_TENANT_MAP`/`OIDC_TENANT_MAP_PATH` configurados. Cualquiera faltante → fail-closed (preserva V5.2).
  - Producción NUNCA cae a DEV. Si OIDC disabled, todos los bearer son 401.
  - AuthContext extendido con campos opcionales `issuer`, `subject`, `email`, `display_name` (default `""` para backward compat con dev/test).
  - 49 tests nuevos (31 scenarios A-Z + 6 tenant isolation + 12 MCP HTTP integration).

- **Evidencia:** Commit V6.0 (por publicar), 1393 passed, 5 skipped, Ruff verde, CI verde en 3.10/3.11/3.12 + clean-room.

- **Condiciones para revisar:** Cuando se integre un OAuth provider real (Auth0/Keycloak), ejecutar los tests V6.0 contra el JWKS del provider en staging. Cuando se añada un nuevo role ALBRA, actualizar `ALBRA_ROLES` y `RoleMapping.allowed_roles`.

---

## D-V8.0-F2 — Validación jurídica: VigencyChecker + ContradictionDetector + AdversarialValidator

- **Identificador:** D-V8.0-F2
- **Fecha:** 2026-10-29
- **Estado:** APPROVED
- **Contexto:** V8.0 Fase 1 cerró las brechas de cobertura del corpus (B1-B4). Fase 2 cierra B6 (validación de vigencia) y B7 (detección de contradicciones).

- **Decisión:** Implementar 3 módulos nuevos + integración en LawyerExam pasos 7 y 11.

- **VigencyChecker**: opera sobre document-level (`status`, `effective_until`) + article-text markers ("modificado por", "derogado por", "sustituido por", "texto original revivido"). Retorna vigent | modified | superseded | uncertain. REGLA CRÍTICA: ausencia de info ≠ evidencia de vigencia → uncertain.

- **ContradictionDetector**: clasifica pares de citas como explicit_conflict | modification | complementary | not_determinable. CONSERVADOR: default = not_determinable.

- **AdversarialValidator**: envuelve los dos anteriores. Defectos con severity blocking/warning/info. Blocking → ok=False → LawyerExam BLOCKED.

- **LIMITACIÓN B7 EXPLÍCITA**: ContradictionDetector no dispone de implementación efectiva para `explicit_conflict`. La función `_check_explicit_conflict_markers()` retorna vacío. En la práctica, el sistema utiliza `not_determinable` como abstención. Esto NO debe corregirse con inferencias semánticas o reglas inventadas. B7 queda como LIMITACIÓN / TRABAJO PENDIENTE.

- **Alternativas consideradas:**
  - *Inferencia semántica de conflictos* — RECHAZADO: sin ontología jurídica, la inferencia genera falsos positivos.
  - *Reglas jurídicas hard-coded* — RECHAZADO: inventaría conocimiento jurídico.
  - *Similitud textual* — RECHAZADO: similitud ≠ contradicción.

- **Consecuencias:**
  - El LawyerExam NO puede declararse SUCCESS cuando una norma citada está demostrablemente derogada.
  - El caso piloto V7.0 (arts. 28/29/30) continúa funcionando: estas normas son vigent sin marcadores de modificación.
  - Paso 9 (procesal) ABSTAINED preservado.
  - 19 tests nuevos. 1466 total. CI verde.

- **Evidencia:** Commit `1e4ad53`, CI Run `40876863242` SUCCESS, 1466 passed.

---

## D-V8.0-F3 — Referencias normativas deterministas y paso 9 condicional

- **Identificador:** D-V8.0-F3
- **Fecha:** 2026-10-30
- **Estado:** APPROVED
- **Contexto:** Fase 2 cerró B6 (vigencia) y B7 quedó como PARCIALMENTE RESUELTA (sin contradicción semántica). Fase 3 cierra la cobertura de trazabilidad de cross-references artículo→artículo dentro del corpus V1.4 y endurece el paso 9 procesal con activación condicional estricta.

- **Decisión:** Introducir un módulo nuevo `albra/knowledge/norm_reference.py` con `NormReference` (dataclass frozen) y reescribir `_step_09_procedural_requirements()` en `albra/lawyer/exam.py` con 4 guards estrictos. Sin alterar VigencyChecker, ContradictionDetector, AdversarialValidator, RealProviderGuard ni ningún contrato de seguridad existente.

- **NormReference — disciplina:**
  - Resuelve cross-references artículo→artículo con regex determinista (sin LLM, sin inferencia semántica).
  - `reference_type` siempre = `"references"` (informativa) — NUNCA `contradiction`, `modification`, `incompatibility` ni `prevalence`.
  - `confidence` solo admite `"verified"` (source y target en V1.4) o `"uncertain"` (en caso contrario). NO existe `inferred`.
  - Jerarquía normativa DERIVADA del `document_type` (Constitución=1, ley/codigo_sustantivo=2, desconocido=999). NO se almacena en la referencia. NO existen `hierarchy_higher`/`hierarchy_lower` como campos.
  - Frases informativas (`de conformidad con`, `con arreglo a`, `según lo dispuesto en`, `en los términos del artículo`) NO se convierten en contradicción, modificación, incompatibilidad ni prevalencia.
  - `uncertain` NUNCA bloquea: `NormReference` no es consumido por `AdversarialValidator`. Es exclusivamente metadata de trazabilidad.

- **Paso 9 — disciplina condicional:**
  1. `procedure_type` es EXPLÍCITO: leído de `case_facts.get("procedure_type", "")`. Nunca inferido por keywords.
  2. Si ausente → ABSTAINED. Si no soportado (`civil`/`penal`/`conciliación`) → ABSTAINED. Si código procesal no en V1.4 → ABSTAINED. Si sin artículos con keywords procesales → ABSTAINED.
  3. Las keywords (`término`, `plazo`, `competencia`, `juzgado`, `audiencia`, `notificación`, `recurrido`, `interpone`, `substanciación`) recuperan ÚNICAMENTE evidencia contextual dentro del código procesal ya seleccionado.
  4. La salida del paso 9 con `status="ok"` incluye disclaimer explícito: *"los artículos presentados son resultado de una búsqueda por keywords, no de un análisis jurídico del procedimiento aplicable. Requieren revisión por abogado humano para confirmar relevancia y aplicabilidad."*

- **Alternativas consideradas:**
  - *Inferir `procedure_type` por keywords del caso* — RECHAZADO: una keyword no determina un procedimiento jurídico.
  - *Convertir referencias informativas en contradicciones implícitas* — RECHAZADO: `de conformidad con` ≠ oposición.
  - *Resolver referencias externas vía LLM* — RECHAZADO: el LLM no puede crear relaciones `verified`.
  - *Almacenar jerarquía como campo de la referencia* — RECHAZADO: la jerarquía es propiedad del `document_type`, no de la referencia.
  - *Inventar rangos jurídicos para tipos desconocidos* — RECHAZADO: tipo desconocido → `999` / `"unknown"`.

- **Consecuencias:**
  - 127 referencias totales resueltas (44 verified + 83 uncertain) sobre el corpus V1.4 real.
  - `NormReference` no es importado por ningún módulo bajo `albra/` fuera de `norm_reference.py`. Las 44 verified **no cambian ninguna decisión del motor** — aportan exclusivamente trazabilidad determinista (opción B).
  - Paso 9 del caso piloto V7.0 (habeas corpus, sin `procedure_type`) sigue ABSTAINED.
  - B7 continúa como PARCIALMENTE RESUELTA. Fase 3 NO introdujo detección de contradicción semántica.
  - 19 tests nuevos. 1497 total. CI verde.

- **Evidencia:** Commit `0c886be`, CI Run `40980036870` SUCCESS (lint + 3.10/3.11/3.12 + clean-room), 1497 passed.

- **Condiciones para revisar:** Cuando se añadan nuevos `document_type` reconocidos al corpus, extender `_HIERARCHY_RANK` en `norm_reference.py`. Cuando se añadan nuevos códigos procesales al corpus V1.4, extender `proc_map` en `exam.py` paso 9. Cuando se desee detección semántica de contradicciones, requires ontología jurídica formal — fuera del alcance de Fase 3.

