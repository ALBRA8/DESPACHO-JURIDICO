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
