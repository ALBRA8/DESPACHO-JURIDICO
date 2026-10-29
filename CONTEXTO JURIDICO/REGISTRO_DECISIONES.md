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
