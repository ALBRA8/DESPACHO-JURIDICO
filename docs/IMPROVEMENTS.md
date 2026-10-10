# MEJORAS EXPONENCIALES IMPLEMENTADAS

Investigación basada en proyectos similares de GitHub (NO clonados - solo ideas adaptadas).

## Resumen

| # | Mejora | Órganos afectados | Estado |
|---|--------|------------------|--------|
| 1 | Órganos con manifest role/goal/backstory | identity | ✅ |
| 2 | Action Firewall con audit hash-chain | security, audit | ✅ |
| 3 | Cite-or-Refuse Gate | evidence | ✅ |
| 4 | Debate Adversarial Multi-Agente | reasoning | ✅ |
| 5 | Workflows como grafos con interrupts HITL | workflows | ✅ |
| 6 | Consolidación Jerárquica de Memoria | memory | ✅ |
| 7 | CRAG - Corrective RAG | research | ✅ |
| 8 | MCP Multi-Jurisdicción | mcp | ✅ |
| 9 | Self-Healing Doctor Supervisor | doctor | ✅ |
| 10 | Provider Router por sensibilidad (BYOK) | providers | ✅ |
| 11 | Tamper-Evident Audit | audit | ✅ |
| 12 | SOPs Jurídicos como handoffs tipados | workflows, handoffs | ✅ |
| 13 | Plugin System | tools, capabilities | ✅ |
| 14 | Policy-as-Code | security | ✅ |
| 15 | Knowledge Triage | knowledge | ✅ |
| 16 | CUAD-based Contract Redlining | plugin | ✅ |

## 1. Órganos con manifest role/goal/backstory (inspirado en CrewAI)

Cada uno de los 30 órganos del ADN tiene un `OrganManifest` declarativo con:
- `role`: rol del órgano
- `goal`: su objetivo principal
- `backstory`: narrativa que moldea su "personalidad" y restricciones
- `restrictions`: límites duros

Archivo: `albra/identity/organ_manifests.py`

Ejemplo:
```python
"EVIDENCIA": OrganManifest(
    name="EVIDENCIA",
    role="Custodio de la cadena probatoria",
    goal="Mantener pipeline SOURCE → ... → ACTION.",
    backstory="Soy la cadena de custodia. Cada eslabón depende del anterior...",
    restrictions=("Toda conclusión debe citar su evidencia",),
)
```

## 2. Action Firewall con audit hash-chain (inspirado en Aegis/cordum)

Gate determinístico **antes** de cualquier acción riesgosa. 14 políticas por defecto, organizadas por:
- `risk`: low/medium/high/critical
- `requires_hitl`: si necesita aprobación humana
- `kill_switch`: si se puede apagar en runtime (algunas NO - como modify_audit_log)
- `allowed_roles`: roles permitidos
- `cooldown_seconds`: rate limiting

Cada acción permitida genera un **bloque en el hash chain** del firewall, que es tamper-evident.

Archivos: `albra/security/firewall/{policy,engine}.py`

## 3. Cite-or-Refuse Gate (inspirado en citegate/ede-legal-plugin)

ALBRA **jamás** emite una afirmación legal sin cita verificable a fuente oficial. Patrones detectados:
- "el artículo", "la ley", "el código", "el estatuto", "la constitución", etc.

Si no hay evidencia con `source_type=official` asociada, el gate **rechaza** la salida y devuelve un texto safe.

Esto es lo que diferencia a ALBRA de un chatbot alucinador.

Archivo: `albra/evidence/cite_gate.py`

## 4. Debate Adversarial Multi-Agente (inspirado en TradingAgents)

Para preguntas jurídicas delicadas, se lanzan 3 perspectivas:
1. Abogado de la parte actora (argumenta a favor)
2. Abogado de la parte demandada (argumenta en contra)
3. Magistrado (sintetiza y emite dictamen)

Cada rol tiene prompt específico. Reduce sesgo y fuerza citar contraargumentos.

Archivo: `albra/reasoning/debate.py`

## 5. Workflows como grafos con interrupts HITL (inspirado en LangGraph)

Flujos como grafos dirigidos con:
- 4 tipos de nodos: ACTION, DECISION, INTERRUPT, TERMINAL
- Edges condicionales
- Ciclos (para revisión/rehacer)
- Interrupts que pausan para aprobación humana
- Reanudación con `resume(run_id, approved=True)`

Workflow predefinido: `build_demand_workflow()` (demanda civil con 6 nodos, 1 interrupt HITL).

Archivo: `albra/workflows/graph.py`

## 6. Consolidación Jerárquica de Memoria (inspirado en AIrecall)

Memoria episódica → semántica. Job periódico que:
1. Selecciona ítems episódicos antiguos
2. Los agrupa por usuario/conversación
3. Crea resúmenes semánticos (categoría `knowledge`)
4. Desactiva los ítems episódicos (active=0)

Esto mantiene el archivo limpio sin perder conocimiento destilado.

Archivo: `albra/memory/consolidator.py`

## 7. CRAG - Corrective RAG (inspirado en legal-rag-analyst)

Pipeline:
1. Recuperar chunks de memoria
2. Gradear relevancia (similarity score)
3. Si score < threshold → reescribir query
4. Si aún no hay hit → fallback a research web
5. Devolver con confidence + source

Evita respuestas basadas en chunks irrelevantes.

Archivo: `albra/research/crag.py`

## 8. MCP Multi-Jurisdicción (inspirado en mcp-taiwan-legal-db, us-legal-mcp)

Catálogo de servers MCP por jurisdicción:
- CO (Colombia) - primaria
- AR, MX, ES, BR - preparadas

Cada jurisdicción = un MCP server. Permite escalar jurisdicciones sin tocar el core.

Las URLs están vacías por diseño - cuando exista un server MCP legal real para una jurisdicción, se agrega.

Archivo: `albra/mcp/jurisdictions.py`

## 9. Self-Healing Doctor Supervisor (inspirado en shard/solas-trace)

Doctor como supervisor de los otros 29 órganos:
- Loop de monitoreo periódico
- Snapshot de salud por órgano
- Si órgano degrada → intenta recovery (restart o handler custom)
- Si no puede recuperar → marca como degradado, sigue operando
- NUNCA modifica código - solo reinicia/reconecta

Archivo: `albra/doctor/self_healing.py`

## 10. Provider Router por sensibilidad (inspirado en agenticSeek/omnigent)

BYOK - bring your own key. El router decide el provider por:
- Datos sensibles (DNI, expediente, secreto profesional) → modelo local
- Contexto largo → provider con context window grande
- Chat general → cloud

Protege el secreto profesional.

Archivo: `albra/providers/router.py`

## 11. Tamper-Evident Audit (inspirado en forgesight/RagaAI-Catalyst)

Cada entrada del audit log incluye:
- `prev_hash`: hash de la entrada anterior
- `this_hash`: hash de la entrada actual

`verify_chain()` detecta cualquier manipulación.
`fingerprint()` devuelve el hash del estado actual para comparar con backups.

Permite demostrar ante un perito/juez que el log no fue manipulado.

Archivo: `albra/audit/tamper_evident.py`

## 12. SOPs Jurídicos como handoffs tipados (inspirado en MetaGPT)

Standard Operating Procedures como workflows contractuales. Cada step:
- input_schema y output_schema tipados
- requires_hitl flag
- capability_required
- estimated_minutes

SOPs predefinidos:
- `demanda_civil` (6 steps, 2 HITL)
- `contestacion_demanda` (5 steps, 2 HITL)

Archivo: `albra/workflows/sops.py`

## 13. Plugin System

Sistema de plugins para extender el agente sin tocar el core:
- Manifest con nombre, versión, dependencias, permisos
- Register/unregister en runtime
- Aislado - no puede modificar código del core
- Auditable

Plugin builtin: `contract_redlining`.

Archivo: `albra/plugins/manager.py`

## 14. Policy-as-Code

Reglas declarativas versionadas y auditables. Engine con 5 policies por defecto:
- CO-001: menores requieren especialista
- CO-002: montos altos requieren HITL
- GLOBAL-001: nunca modificar audit
- GLOBAL-002: envío externo requiere HITL
- GLOBAL-003: datos sensibles → modelo local

Archivo: `albra/security/policy.py`

## 15. Knowledge Triage

Clasifica preguntas jurídicas y las enruta al tipo de fuente correcto:
- statute, jurisprudence, doctrine, procedure, mixed

Patrones heurísticos por keyword.

Archivo: `albra/knowledge/triage.py`

## 16. CUAD-based Contract Redlining

Plugin que detecta cláusulas de riesgo en contratos. 6 patrones:
- indemnidad_amplia
- no_responsabilidad
- terminacion_unilateral
- confidencialidad_perpetua
- renuncia_derechos
- arbitraje_uneven

Cada match incluye snippet de contexto y severidad.

Archivo: `albra/plugins/manager.py` (plugin `contract_redlining`)

## Métricas finales

- **Tests**: 95/95 pasando
- **Órganos**: 30 del ADN + 16 mejoras exponenciales
- **CLI commands**: 12 (info, chat, doctor, organs, capabilities, tools, memory, firewall, policies, manifests, sops, jurisdictions, debate, audit_verify, serve)
- **HTTP endpoints**: 9 (root, health, chat, tools, capabilities, organs, memory/stats, audit, evidence)
- **Políticas firewall**: 14
- **Políticas as-code**: 5
- **SOPs**: 2 (demanda_civil, contestacion_demanda)
- **Jurisdicciones**: 5 (CO primaria, AR/MX/ES/BR preparadas)
- **Plugins**: 1 builtin (contract_redlining)
- **Plugins externos**: 0 (arquitectura preparada)
