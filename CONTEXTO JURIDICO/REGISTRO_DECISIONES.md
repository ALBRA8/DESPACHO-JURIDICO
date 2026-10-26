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
