# DESPACHO JURÍDICO — ESTADO ACTUAL

- **Estado del documento:** `V5.1.1 CIERRE FINAL DEL GUARD DE CLI (FAIL-CLOSED)`
- **Última revisión documental:** 2026-10-29
- **Repositorio:** `ALBRA8/DESPACHO-JURIDICO`
- **HEAD inicial V5.1.1:** `c492a5d` (V5.1 CURRENT_STATE)
- **HEAD final V5.1.1:** `19d045f` (V5.1.1 CLI guard fail-closed)
- **Push:** VERIFIED (c492a5d..19d045f main)
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
