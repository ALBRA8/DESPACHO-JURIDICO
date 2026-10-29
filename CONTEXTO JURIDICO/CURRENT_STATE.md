# DESPACHO JURÍDICO — ESTADO ACTUAL

- **Estado del documento:** `ACTUALIZADO — OLEADAS 0 + 1 COMPLETADAS`
- **Última actualización:** 2026-10-28
- **Repositorio:** `ALBRA8/DESPACHO-JURIDICO`
- **Rama:** `main`
- **HEAD actual:** `72a75c1f193ef337589a01972efd1d87877ee642`
- **HEAD anterior de baseline:** `cc0780db71fcbf6b11643ba7c5271c155d520441`
- **Estado funcional global:** `AGENTE JURÍDICO EN CONSTRUCCIÓN — BASE FUNCIONAL + HARDENING MCP COMPLETADO`
- **Veredicto de producción:** `NO CERTIFICADO COMO PRODUCTION READY`; quedan mega-oleadas de integración, corpus/provenance, security, motor jurídico, LLM/RAG, observabilidad y aceptación final.

> Este documento distingue entre capacidades implementadas, validaciones ejecutadas por el Constructor y validaciones independientes. La existencia de un componente no implica por sí sola que todo el flujo de producción esté certificado.

## 1. Propósito del proyecto

Construir un **agente jurídico colombiano digital**, con jurisdicción inicial en Colombia, utilizando una arquitectura de agente profesional separada de sus capacidades y de su conocimiento jurídico verificable.

El objetivo actual no es construir simplemente un software jurídico tradicional. El proyecto está evolucionando hacia un **agente abogado especializado**, con infraestructura de ejecución, seguridad, conocimiento jurídico, evidencia, citas, playbooks, LLM/RAG y capacidades MCP.

### Estado conceptual actual

El proyecto ya dispone de una base suficiente para considerar que existe un **agente jurídico en construcción real**: cuerpo técnico, controles de ejecución, herramientas jurídicas, conocimiento estructurado y rutas MCP.

Todavía no debe describirse como un abogado completamente terminado o certificado para producción. Las próximas mega-oleadas deben cerrar la integración de extremo a extremo y las limitaciones restantes.

---

## 2. Baseline y evolución reciente

### Baseline de OLEADA 0

- HEAD inicial: `cc0780d`
- Tests baseline: **1242 passed, 5 skipped**
- Ruff: **All checks passed**
- Working tree: limpio
- Local = Remote según reporte de Constructor
- Inventario reportado: **173 archivos Python, 78 archivos de tests**

### OLEADA 1 — MCP HARDENING

OLEADA 1 queda completada en dos commits:

#### `466c865`

**HTTP AuthContext propagation — cierre de ruta de escalada de privilegios**

- `McpHttpServer` deja de invocar `call_tool(name, args)` sin `auth_context`.
- Bearer token → `validate_bearer_token(...)` → `AuthContext` → `call_tool(..., auth_context=ctx)`.
- La identidad autenticada no se deriva de datos enviados por el usuario.
- Role y permisos se derivan de `AuthContext`.
- Se preservan `request_id` y `correlation_id` para auditoría.
- Se cubre el intento de override de rol mediante argumentos.

#### `72a75c1`

**stdio AuthContext propagation — cierre de la ruta stdio**

- `McpServer` mantiene `_stdio_auth_context`.
- `initialize` puede recibir `auth.token`.
- El token se valida mediante `validate_bearer_token(token, mode=self._security_mode)`.
- `tools/call` pasa el `AuthContext` a `call_tool`.
- En producción, ausencia de autenticación debe producir comportamiento fail-closed.
- Se mantiene compatibilidad controlada en dev.

El commit actual `72a75c1` contiene estos cambios en `albra/mcp/server.py` y su mensaje registra la suite de **1253 passed, 5 skipped** y Ruff limpio. La existencia y contenido del commit han sido comprobados directamente en GitHub.

---

## 3. Seguridad y control de ejecución — estado actual

### VERIFICADO

- `ExecutionGuard`.
- RBAC.
- `LegalGate` como componente integrado en la ruta endurecida.
- Modelo de `AuthContext`.
- Propagación de identidad en MCP HTTP.
- Propagación de identidad en MCP stdio.
- Auditoría MCP estructurada.
- Prevención de override de rol mediante argumentos en las pruebas de Oleada 1.

### Pruebas adversariales reportadas — `test_execution_guard_wiring.py`

Se reportaron 8 pruebas adversariales, incluyendo:

1. RBAC DENY: cliente + `eval.run` → DENIED.
2. RBAC ALLOW + GUARD DENY: admin + `kill_switch` → GUARD DENY.
3. RBAC ALLOW + GUARD ALLOW: admin + default → ejecución.
4. LEGAL GATE DENY: `BlockingLegalGate` → bloqueo detectado por guard.
5. Cadena autorizada completa → ejecución + auditoría.

### Auth propagation — `test_http_auth_propagation.py`

Se reportaron 11 pruebas incluyendo:

- token de abogado → role `abogado`;
- token de paralegal → role `paralegal`;
- ausencia de token con OAuth requerido → 401;
- token vacío → 401;
- producción → 401 para tokens no válidos;
- producción rechaza tokens scaffold;
- autorización por rol para `eval.run`;
- auditoría basada en identidad autenticada;
- ausencia de role override por argumentos;
- compatibilidad dev.

### Auditoría MCP

`McpAuditLog` registra, según la implementación y pruebas reportadas:

- actor;
- role;
- auth_method;
- tool/action;
- resultado de autorización;
- motivo de denegación;
- hash SHA-256 de input;
- hash SHA-256 de output;
- `matter_id`;
- `correlation_id`;
- `request_id`;
- status;
- latency;
- error;
- environment.

Se reporta redacción de secretos/tokens/passwords y prueba asociada.

### Limitación pendiente

La seguridad está mucho más avanzada que en V2.5, pero todavía falta una certificación de **trazado completo de todas las rutas reales** para demostrar que ninguna entrada alternativa puede saltarse `AuthContext`, RBAC, LegalGate, ExecutionGuard o auditoría.

---

## 4. Autenticación por entorno

### Producción

El comportamiento implementado en Oleada 1 es **fail-closed** para el scaffold actual: `validate_bearer_token` no acepta arbitrariamente cualquier bearer en producción.

### Dev/Test

Se mantiene autenticación controlada para pruebas y compatibilidad:

- tokens de prueba con roles;
- scaffold OAuth en dev/test;
- compatibilidad con rutas históricas de desarrollo cuando corresponde.

### Limitación externa pendiente

La autenticación/OAuth de producción real todavía requiere una validación con el proveedor de identidad y credenciales/infraestructura reales. No debe confundirse el fail-closed del scaffold con una certificación de OAuth productivo.

---

## 5. Conocimiento jurídico y Corpus

### Corpus V1.1

- Constitución de 1991: 6 artículos.
- Ley 100 de 1993: 3 artículos.
- Ley 80 de 1993: 3 artículos.
- El `content_hash` permite detectar modificaciones del texto almacenado.
- El `raw_content` histórico es texto reconstruido, no HTML crudo.

### Corpus V1.2

- Constitución de 1991: artículos 1–32.
- Ley 100 de 1993: 45 artículos.
- Ley 80 de 1993: 48 artículos.
- Total reportado: **125 artículos**.
- Existe `CitationAuditor` indexando el corpus V1.2.
- Se utilizó Playwright en la ingestión de fuentes JS-driven.

### Limitación de provenance

El corpus histórico V1.2 conserva texto reconstruido, no el HTML original byte-a-byte.

Por tanto:

- modificación del texto almacenado → detectable mediante hash;
- coincidencia byte-a-byte con la fuente original → **NOT VERIFIED**;
- conservación y hash del HTML original → **NOT VERIFIED**;
- source → byte provenance histórico → **NOT VERIFIED**.

No se deben fabricar bytes históricos que nunca fueron preservados.

La siguiente mega-oleada debe resolver la provenance completa para nuevas ingestiones y establecer una estrategia explícita para el corpus legacy.

---

## 6. Capacidades jurídicas existentes

El repositorio ya contiene, entre otras, estas capacidades:

- Matters y state machine.
- Timeline JSONL.
- Agent organigrama.
- Citation audit fail-closed.
- Approval chain / human signoff.
- Matter audit con hash chain SHA-256.
- DeadlineGuard.
- ContradictionGuard.
- AgenticCitator.
- Redline DOCX.
- RAG local TF-IDF.
- Pipeline adversarial RED→BLUE.
- Playbooks laboral, civil, constitucional, familia y corporativo.
- Eval Suite.
- Citation graph.
- IngestionCoordinator.
- LLM provider abstraction/scaffold.
- LLMRouter integrado en AdversarialPipeline.
- Scheduled agents.
- Memory Cell.
- Precedent Board.
- Tabular review.
- Skills marketplace.
- White-label/multi-tenant.
- X402 paid-agent matrix.
- Install log con hash chain.

Estas capacidades constituyen el **arnés jurídico actual** del agente, pero todavía deben validarse como flujos integrados de extremo a extremo.

---

## 7. LLM / RAG

### Implementado

Existe arquitectura de providers para:

- Mock.
- Anthropic.
- OpenAI.
- Ollama.

Existe `LLMRouter` y su integración con el pipeline adversarial.

### Estado

- Mock: **VERIFIED** para pruebas locales.
- Anthropic/OpenAI: requieren credenciales/API reales para certificación externa.
- Ollama: existe integración HTTP, pero la disponibilidad de un servidor Ollama real depende de infraestructura externa/local.

### Pendiente

Cerrar validación de:

- fallback;
- timeouts;
- retries;
- respuestas inválidas;
- grounding;
- prompt injection;
- límites de contexto/tokens;
- comportamiento sin proveedor;
- integración real con RAG y CitationAuditor.

---

## 8. MCP

### Estado actual

MCP dispone de:

- transporte stdio;
- transporte HTTP;
- autenticación por `AuthContext`;
- RBAC;
- ExecutionGuard;
- LegalGate;
- auditoría estructurada;
- herramientas registradas;
- scaffold OAuth.

### OLEADA 1 — resultado

Las dos rutas críticas, HTTP y stdio, ya no deben ejecutar herramientas pasando directamente de entrada a handler sin contexto de autenticación.

El commit `72a75c1` muestra explícitamente que `tools/call` pasa `auth_context=self._stdio_auth_context` y que `initialize` extrae y valida el token cuando se proporciona.

### Pendiente

- smoke runtime independiente de HTTP;
- integración con OAuth/IdP real;
- trazado exhaustivo de todas las rutas de herramientas;
- pruebas de concurrencia/sesiones si aplican;
- certificación final de bypass resistance.

---

## 9. Estado de testing

### Baseline

**1242 passed, 5 skipped.**

### Después de Oleada 1

**1253 passed, 5 skipped.**

El Constructor reporta:

- Ruff: `All checks passed`.
- Python 3.10/3.11/3.12: green.
- clean-room: green.
- GitHub Actions runs `40790799960` sobre `466c865` y `40791431796` sobre `72a75c1`: `SUCCESS`.

**Nota de evidencia:** estos CI runs son registrados aquí como resultados reportados por el Constructor. La auditoría independiente actual verificó el HEAD y el contenido del commit, pero el endpoint de estados consultado para `72a75c1` no devolvió statuses; por tanto no se debe presentar este documento como una certificación independiente del CI.

---

## 10. Documentación relevante

- `docs/ARCHITECTURE.md`
- `docs/CONSTRUCCION_V2.md`
- `docs/LEGAL_V2.md`
- `docs/CORPUS_PILOT_AUDIT_V1.md`
- `docs/CORPUS_PILOT_AUDIT_V1_1.md`
- `docs/AUDIT_INDEPENDENT_V1.md`
- `docs/AUDIT_INDEPENDENT_V2.md`
- `docs/V1.6_INTEGRATION_COMPLETE.md`
- `docs/FINAL_REPORT.md`
- `docs/PARITY_REPORT.md`
- `docs/IMPROVEMENTS.md`
- `CONTEXTO JURIDICO/CURRENT_STATE.md`
- `CONTEXTO JURIDICO/PROVENANCE_V1_2.md`

Este `CURRENT_STATE.md` supersede las referencias anteriores al HEAD `392f416` como estado actual.

---

## 11. Próximas MEGA-OLEADAS

No se trabajará defecto por defecto como estrategia principal. Las siguientes fases deben ejecutarse como **bloques completos de arquitectura**, cerrando cada dominio de extremo a extremo.

### Mega-Oleada A — Seguridad y control

Cerrar el tracing completo de:

`entrada → autenticación → AuthContext → RBAC → LegalGate → ExecutionGuard → herramienta → auditoría → salida`.

Además: SSRF, path traversal, deserialización, secretos, aislamiento, multi-tenancy, privilege escalation y trust escalation.

### Mega-Oleada B — Data Boundary + Ingestión + Corpus

Cerrar:

`fuente → fetch → autenticación → ingestión → normalización → provenance → almacenamiento → retrieval → LLM → evidencia`.

### Mega-Oleada C — Motor jurídico

Cerrar vigencia, derogación, versiones, jurisdicción, conflictos normativos, jurisprudencia, jerarquía normativa, CitationAuditor, evidencia, citas y playbooks como flujo integrado.

### Mega-Oleada D — LLM/RAG/Providers

Cerrar providers, fallback, resiliencia, grounding, RAG, contexto, prompt injection y comportamiento sin proveedor.

### Mega-Oleada E — Operación/Observabilidad

Cerrar audit trail, correlation/request IDs, métricas, errores, lifecycle, recovery, shutdown y reconstrucción de operaciones.

### Mega-Oleada F — Testing de sistema

Ejecutar matriz masiva unit/integration/e2e/adversarial/security/regression/MCP/corpus/temporalidad/LLM/RAG/clean-room.

### Mega-Oleada G — Producción

Cerrar configuración, secrets, modos de ejecución, dependencias, reproducibilidad, CI, deployment readiness y documentación.

Después de estas mega-oleadas debe realizarse una **auditoría independiente final**.

---

## 12. Regla de clasificación

Cada capacidad debe terminar clasificada exactamente como una de estas categorías:

- `VERIFIED`
- `VERIFIED WITH LIMITATIONS`
- `NOT VERIFIED`
- `NOT IMPLEMENTED`
- `LOCAL ONLY`
- `BLOCKED BY EXTERNAL DEPENDENCY`

No se debe elevar una capacidad de categoría simplemente porque exista el código o porque un Constructor haya declarado que funciona.

---

## 13. Veredicto actual

> **DESPACHO-JURIDICO — AGENTE JURÍDICO EN CONSTRUCCIÓN REAL**
>
> **OLEADAS 0 + 1 COMPLETADAS.**
>
> Existe una base funcional jurídica considerable y el control MCP fue endurecido para propagar identidad autenticada por HTTP y stdio.
>
> **Todavía NO está certificado como `PRODUCTION READY — VERIFIED`.**
>
> El objetivo inmediato es continuar con mega-oleadas integrales hasta cerrar las limitaciones internas y separar con evidencia las dependencias que requieren infraestructura o credenciales externas.
