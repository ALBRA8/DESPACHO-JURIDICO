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

---

## D-V8.0-F4 — Draft Citation Audit + VigencyChecker FP fix + stale text V1.3→V1.4

- **Identificador:** D-V8.0-F4
- **Fecha:** 2026-10-30
- **Estado:** APPROVED
- **Contexto:** La auditoría profunda pre-Fase 4 (sobre commit `411977d`) identificó 3 riesgos de falsa capacidad jurídica con candidato a solución mínima: (1) drafts LLM pueden contener citas alucinadas sin detección determinista; (2) VigencyChecker tiene 1 falso positivo confirmado (Constitución art. 62 "modificado por el legislador"); (3) 9 strings stale en exam.py dicen "V1.3" cuando el lookup real usa V1.4 (subrepresentación de cobertura + LLM abstiene incorrectamente). El diseño formal produjo dictamen DESIGN READY FOR IMPLEMENTATION con 3 candidatos P0/P1/P1.

- **Decisión:** Implementar los 3 candidatos en orden de complejidad creciente (Candidato 3 → 2 → 1), conforme al diseño aprobado. Sin extender alcance, sin introducir nuevas capacidades, sin ontología jurídica, sin contradicción semántica, sin inferencia de aplicabilidad, sin nuevos agentes.

- **Candidato 1 (P0) — Draft Citation Audit determinista:**
  - Nuevo método `_audit_draft_citations()` en `LawyerExam`, ejecutado entre step 10 (draft) y step 11 (review).
  - Reutiliza `CitationAuditor.extract_citations()` para extraer citas del `drafted_document`.
  - Normaliza cada cita a slug V1.4 vía alias map + V1.4 `doc["number"]` lookup + sentencia slash→hyphen.
  - Cita a norma externa NO en V1.4 → BLOCKING defect en `result.draft_citation_defects` (campo nuevo).
  - Cita a artículo adicional de norma V1.4 verificada → WARNING (limitation; no blocking).
  - Disclaimer permanente: NO verifica fidelidad de paráfrasis ni aplicabilidad jurídica.
  - Cierra riesgo O.1, O.2, O.9 (subtipo "citas a normas inexistentes").

- **Candidato 2 (P1) — VigencyChecker false positives fix:**
  - Negative lookahead aplicado a 5 markers (`modificado/adicionado/subrogado/sustituido/derogado por`) en `vigency.py` Y `contradiction.py`.
  - Exclusiones: `el legislador`, `el gobierno`, `el reglamento`, `la presente Ley`, `esta Ley`.
  - Único falso positivo corregido: Constitución art. 62 (modified → vigent). Total modified en V1.4: 86 (era 87).
  - True positives preservados: Constitución arts. 77, 96, 111, 112, 303, 361 siguen modified.
  - Consistencia VigencyChecker ↔ ContradictionDetector preservada (unificación Fase 2.2 extendida).

- **Candidato 3 (P1) — Stale text V1.3 → V1.4:**
  - 9 strings stale en `exam.py` actualizados de "V1.3" → "V1.4": docstrings, std_limitations (coverage + jurisprudencia), step 5/6 summaries/notes, step 7/10/11 LLM prompts.
  - Limitations estándar ahora enumeran los 5 cuerpos legales de V1.4 con conteos (2107 artículos total) + 5 sentencias T-xxx-2020.
  - 4 menciones "V1.3" preservadas: documentan el fallback V1.4→V1.3 (defensa en profundidad).
  - Cierra riesgo O.8 (subrepresentación de cobertura + LLM abstiene incorrectamente).

- **Alternativas consideradas (todas RECHAZADAS en la auditoría pre-Fase 4):**
  - *Detector semántico de contradicciones (cerrar B7 4.5)* — RECHAZADO: requiere ontología jurídica, sin definición precisa.
  - *Nueva capa de aplicabilidad normativa (sujeto/conducta/materia/ámbito)* — RECHAZADO: sobreconstrucción sin caso de uso.
  - *Pool de especialistas (`specialists.py`)* — RECHAZADO: placeholders sin valor inmediato.
  - *Ampliación de corpus (Código Civil, CPACA, etc.)* — RECHAZADO para Fase 4: requiere pipeline de ingesta.
  - *Verificación de fidelidad de paráfrasis vía NLI* — RECHAZADO: requiere modelo ML externo.
  - *Knowledge graph / citation graph wiring* — RECHAZADO: sobreconstrucción sin consumidor.

- **Consecuencias:**
  - 46 tests nuevos (12 stale text + 22 vigency FP + 12 draft audit). Suite completa: 1543 passed, 7 skipped, 0 failed.
  - Drafts con citas alucinadas ahora se bloquean deterministamente antes de step 11.
  - VigencyChecker produce 1 warning menos (más preciso).
  - LLM recibe prompts que reflejan correctamente V1.4 (puede invocar CGP/CPP/CST/Ley 640 sin abstención incorrecta).
  - B7 continúa PARCIALMENTE RESUELTA — sin cambios.
  - Corpus V1.3, V1.4, v14_raw, AGENTE-GENERAL, RealProviderGuard, RBAC/OIDC/auth/audit intactos.

- **Evidencia:** Commit `02a7ea3`, CI Run `40985592270` SUCCESS (lint + 3.10/3.11/3.12 + clean-room), 1543 passed.

- **Condiciones para revisar:** Cuando se añadan nuevos formatos de cita jurídica al `CitationAuditor.extract_citations()`, considerar extender `_looks_like_external_norm()` con nuevos patrones. Cuando se detecten nuevos falsos positivos en VigencyChecker, añadir frases al negative lookahead. Cuando se desee verificar fidelidad de paráfrasis, requiere NLI/entailment model — fuera de alcance Fase 4.



---

## DJ-POOL-001 — Dirección arquitectónica inicial del POOL DE ABOGADOS ALBRA

- **Fecha:** 2026-10-29
- **Estado:** `PROPOSED — DESIGN REQUIRED`
- **Origen:** decisión conversacional del usuario sobre organizar especialistas con el patrón de chalecos ALBRA.
- **Decisión conceptual:** orientar el futuro Pool hacia varios agentes especialistas independientes, cada uno basado en `AGENTE-GENERAL` y equipado con un chaleco jurídico propio, en lugar de un único cerebro monolítico que intente conocer todas las ramas del derecho.
- **Ejemplos iniciales propuestos por el usuario:**
  - **MARIO:** `AGENTE-GENERAL + CHALECO LABORAL`.
  - **ANA:** `AGENTE-GENERAL + CHALECO PENAL`.
- **Pool superior:** una futura capa de coordinación que recibe asuntos, enruta a uno o varios especialistas, recoge resultados, conserva trazabilidad y consolida respuestas. No debe presentarse como abogado omnisciente ni reemplazar el análisis especializado.
- **Base de cada especialista:** instancia/proyecto propio derivado de `AGENTE-GENERAL`; el repositorio central `AGENTE-GENERAL` permanece intacto. La especialidad se aporta mediante el chaleco, sus fuentes, reglas, pruebas y límites.
- **Relación con DESPACHO JURÍDICO V8.0:** V8.0 permanece como primera versión funcional aceptada con limitaciones. Será referencia técnica y antecedente; no se convierte automáticamente en Pool, coordinador ni abogado universal.
- **Integración prevista:** evaluar MCP para comunicación y delegación entre Pool y especialistas. No se aprueba aún ningún contrato, servidor, permiso ni flujo de producción.
- **Expansión:** otras especialidades (civil, comercial, administrativo/contencioso, procesal, etc.) quedan como posibilidades sujetas a caso de uso y auditoría; no son una lista de agentes autorizados.
- **Salvaguardas:** separación de corpus, expedientes, permisos y memoria; trazabilidad por especialista; abstención fuera de alcance; revisión humana cualificada antes de actuaciones reales; registro de desacuerdos entre especialistas.
- **Alternativa descartada provisionalmente:** un único agente/cerebro monolítico con todas las ramas jurídicas. Motivo: mezcla de responsabilidades y límites, mayor complejidad de validación y riesgo de aparentar cobertura que no está demostrada.
- **Siguiente paso:** diseño y auditoría de viabilidad sin cambios de código ni creación de agentes. Comparar la arquitectura de repositorios independientes, el rol del Pool, MCP, seguridad, aislamiento y estrategia de piloto.
- **Límite de autorización:** esta decisión registra una dirección conceptual preferida por el usuario. **No autoriza** crear MARIO, ANA, el Pool, repositorios, chalecos, nuevos corpus ni modificar `AGENTE-GENERAL` o `DESPACHO-JURIDICO`. Se requiere diseño formal y autorización explícita posterior.

