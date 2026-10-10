# ARQUITECTURA ALBRA

## 1. Filosofía

ALBRA es un **organismo digital**, no un chatbot. Su diseño sigue 3 principios:

1. **Separación código/conocimiento**: el código vive en GitHub (Constructor). El conocimiento se carga después como datos en la `memory` o en el `knowledge layer`. Nunca se confunden.
2. **ADN completo desde el nacimiento**: los 30 órganos existen desde el día 1, aunque algunos estén en estado `prepared` esperando configuración.
3. **No invención**: ALBRA no inventa APIs, credenciales, integraciones ni conocimiento. Si algo no existe, falla explícitamente.

## 2. Órganos del ADN (30)

```
┌──────────────────────────────────────────────────────────────────┐
│                        AGENTE ALBRA                              │
├──────────────────────────────────────────────────────────────────┤
│  IDENTITY (codename: ALBRA-BASE-V1, jurisdiction: CO)            │
│  RUNTIME (loop plan-act-observe con timeouts y max-iter)         │
│  REASONING (capas: DATA/SOURCES/EVIDENCE/INFERENCES/CONCLUSIONS/ACTIONS)│
│  TOOLS (registry con autorización y trazabilidad)                │
│  CAPABILITIES (9 caps - 3 active, 6 prepared con HITL)           │
│  MCP/MSP (JSON-RPC server + multi-jurisdiction client)            │
│  MEMORY (memorydv - vectorial con 6 categorías separadas)        │
│  DOCTOR (9 checks + self-healing supervisor)                     │
│  MULTIMODAL (text, image, audio, document handlers)              │
│  FILES (tracker con SHA256)                                       │
│  COMMS (router + adapters WA/TG/text/voice)                       │
│  RESEARCH (CRAG - corrective retrieval con web fallback)           │
│  EVIDENCE (cadena con provenance + cite-or-refuse gate)           │
│  SECURITY (auth + authz + firewall + policies)                   │
│  HITL (approval gate para acciones sensibles)                     │
│  EVENTS (bus async con wildcard handlers)                         │
│  WORKFLOWS (graph stateful con interrupts + SOPs)                 │
│  HANDOFFS (protocol para futuros subagentes)                      │
│  PROVIDERS (mock/openai/anthropic + router por sensibilidad)      │
│  RESILIENCE (retry + fallback + recovery)                         │
│  OBSERVABILITY (logger estructurado + metrics + tracer)           │
│  AUDIT (tamper-evident con hash chain)                            │
│  KNOWLEDGE (layer vacío por diseño - Colombia first)              │
└──────────────────────────────────────────────────────────────────┘
```

## 3. Flujo de un mensaje

```
Usuario → Comms adapter → CommsRouter.route_in()
                              ↓
                         EventBus.emit("intake")
                              ↓
                         AuditLog.record("intake")
                              ↓
                         SecurityGate.authorize(user, "chat", risk="low")
                              ↓
                    ┌──────── ReasoningEngine.plan(message) ────────┐
                    │  LAYER_DATA: { raw_message, user, channel }     │
                    │  LAYER_SOURCES: [user_input]                    │
                    │  LAYER_EVIDENCE: [{source, content, ts}]         │
                    │  LAYER_INFERENCES: [{intent, confidence}]       │
                    │  LAYER_CONCLUSIONS: [decisions]                  │
                    │  LAYER_ACTIONS: [{type, tool, input}]           │
                    └─────────────────────────────────────────────────┘
                              ↓
                    MemoryDV.retrieve(query, top_k=5)
                              ↓
                    Para cada step de tipo "tool_call":
                        ToolRegistry.invoke(tool, input, user)
                            ↓
                        ActionFirewall.is_allowed(action, user, role)
                            ↓
                        AuditLog.record("tool.invoke", {result})
                              ↓
                    ReasoningEngine.respond(message, plan, tool_results)
                              ↓
                    CiteOrRefuseGate.evaluate(text, evidence_chain)
                        (si afirmación legal sin cita → refuse)
                              ↓
                    MemoryDV.write(text, category="conversational")
                              ↓
                    AuditLog.record("outtake", {response})
                              ↓
                    CommsAdapter.send(reply)
```

## 4. Pipeline de evidencia

```
SOURCE → INGESTION → EXTRACTION → EVIDENCE → PROVENANCE → ANALYSIS → CONCLUSION → ACTION
```

Cada item de evidencia:
- `id`: identificador único
- `kind`: research_finding | document_extract | user_input | tool_output
- `content`: el texto
- `source`: URL o path de origen
- `obtained_at`: timestamp
- `version`: versión de la fuente
- `transformation`: qué transformación sufrió
- `depends_on`: lista de otros evidence_ids de los que depende
- `metadata`: extra

El método `trace(eid)` reconstruye el árbol de procedencia completo.

## 5. Sistema de capacidades

Cada capability define:

| Campo | Descripción |
|-------|-------------|
| `name` | Identificador |
| `description` | Para qué sirve |
| `required_permissions` | Qué permisos requiere |
| `required_tools` | Tools necesarias |
| `inputs` | Schema de inputs |
| `outputs` | Schema de outputs |
| `risks` | Lista de riesgos |
| `dependencies` | Dependencias externas |
| `state` | active / prepared / planned |
| `requires_human_approval` | HITL obligatorio |

Capacidades activas por defecto:
- `conversation`
- `tool_invocation`
- `health_diagnostic`
- `memory_search`

Capacidades preparadas (requieren configuración externa):
- `document_reading`
- `document_generation` (HITL)
- `legal_research`
- `external_communication` (HITL)
- `knowledge_load` (HITL)

## 6. Action Firewall

Gate determinístico antes de cualquier acción riesgosa. 14 políticas por defecto:

- `send_external_message` (high, HITL)
- `publish_document` (critical, HITL, no kill switch)
- `send_legal_filing` (critical, HITL, no kill switch)
- `delete_evidence` (critical, HITL)
- `modify_audit_log` (critical, DENIED a todos, no kill switch)
- `memory_write_knowledge` (medium)
- `memory_purge` (critical, HITL)
- `modify_permissions` (high, HITL)
- `modify_config` (medium)
- `tool_invocation_low/medium/high`
- `research_external`
- `generate_legal_document` (high, HITL)

Cada acción que pasa queda registrada en un **hash chain** tamper-evident.

## 7. Cite-or-Refuse Gate

ALBRA no emite afirmaciones legales sin cita verificable. Patrones detectados:
- "el artículo", "la ley", "el código", "el estatuto"
- "la constitución", "la jurisprudencia", "el reglamento"
- "la norma", "según la corte", "de acuerdo con"

Si el texto matches y no hay evidencia con `source_type=official`, se rechaza.

## 8. Debate Adversarial

Para preguntas delicadas, el reasoning lanza 3 roles:
1. **Abogado de la parte actora**: argumenta a favor
2. **Abogado de la parte demandada**: argumenta en contra
3. **Magistrado**: sintetiza y emite dictamen

Reduce sesgo y fuerza contraargumentación.

## 9. Workflows como grafos

Los workflows jurídicos se representan como grafos dirigidos con:
- Nodos: ACTION / DECISION / INTERRUPT / TERMINAL
- Edges: con condiciones opcionales
- Ciclos: para revisión/rehacer
- Interrupts: HITL que pausan el flujo

SOPs predefinidos: `demanda_civil`, `contestacion_demanda`.

## 10. Plugin system

Los plugins extienden el agente sin tocar el core. Cada plugin:
- Tiene manifest (nombre, versión, dependencias)
- Registra tools/capabilities/providers via `PluginContext`
- Es aislado y auditable

Plugin builtin: `contract_redlining` (detección de cláusulas de riesgo basado en CUAD).

## 11. Policy-as-Code

Reglas declarativas que el agente cumple. Versionadas, auditables.

Ejemplos:
- `CO-001`: si asunto involucra menor → requiere rol specialist_family
- `CO-002`: si monto > 1000 SMMLV → requiere HITL
- `GLOBAL-001`: nunca modificar audit log
- `GLOBAL-002`: envío externo → requiere HITL

## 12. Knowledge Triage

Clasifica preguntas jurídicas y las enruta al tipo de fuente correcto:
- `statute` → normas
- `jurisprudence` → sentencias
- `doctrine` → doctrina
- `procedure` → procedimental
- `mixed` → múltiples

## 13. Provider Router con BYOK

El router decide el provider por sensibilidad:
- Datos sensibles (DNI, expediente, secreto profesional) → modelo local
- Contexto largo → provider con context window grande
- Chat general → cloud

## 14. Self-Healing Supervisor

Doctor como supervisor de los 29 órganos:
- Monitorea salud periódicamente
- Si órgano degrada → intenta recovery
- Si no puede recuperar → marca como degradado, sigue operando
- Nunca modifica código - solo reinicia/reconecta

## 15. Tamper-Evident Audit

Cada entrada del audit log incluye:
- `prev_hash`: hash de la entrada anterior
- `this_hash`: hash de la entrada actual

`verify_chain()` detecta cualquier manipulación.
`fingerprint()` devuelve el hash del estado actual para comparar con backups.
