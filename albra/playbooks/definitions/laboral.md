---
practice_area: laboral
typical_matter_types:
  - demanda_ordinaria_laboral
  - accion_de_tutela_salud_laboral
  - accion_de_reintegro
  - demanda_indemnizacion_despido_injustificado
  - accion_nulidad_reintegro_convencion_colectiva
workflow_states:
  - NUEVO
  - INTAKE
  - PLANEACIÓN
  - EJECUTANDO
  - BORRADOR-FINAL
  - EN-ESPERA-DE-APROBACIÓN
  - LISTO-PARA-CLIENTE
  - FIRMADO-Y-ENTREGADO
required_documents:
  - poder_judicial.docx
  - demanda.docx
  - certificado_existencia_representacion_legal.eps
  - historia_laboral.pdf
  - liquidacion_definitiva.pdf
  - comunicacion_despido.pdf
deadline_types:
  - prescripcion_laboral_3_years
  - prescripcion_laboral_acciones
  - demanda_contestacion
  - recursos_sentencia
  - impugnacion_sentencia
citation_corpus:
  - Constitución Política de 1991
  - Ley 100 de 1993
red_flags:
  - Si el cliente firmó liquidación sin asesoría → evaluar vicio del consentimiento
  - Si pasaron más de 3 años desde la causal → prescripción probable
  - Si el cliente es servidor público → jurisdicción contencioso-administrativa
  - Si hay convención colectiva → fuero sindical, enviar a jurisdicción ordinaria con fuero
  - Si el despido fue por denuncia sindical → Tutela + acción de reintegro
---

# Playbook Laboral

Role: Guía para DRAFTING-AGENT y REVIEW-AGENT en matters del área laboral
colombiana. Aplica para relaciones de trabajo particulares (no servidores
públicos, que van a lo contencioso-administrativo).

## Etapa 1 · INTAKE

Datos críticos del cliente a recopilar:
- Nombre completo, cédula, dirección, teléfono, email
- Empleador (nombre, NIT, dirección)
- Fecha de ingreso y fecha de retiro
- Causa del despido (con texto literal de la comunicación)
- Salario último devengado
- ¿Firmó liquidación definitiva? (sí/no)
- ¿Hay convención colectiva aplicable?
- ¿Es afiliado a sindicato?

## Etapa 2 · PLANEACIÓN (research)

Cuestiones jurídicas a investigar:
1. Prescripción: ¿3 años o más desde la causal? (Art. 151 CST)
2. Causal de despido: ¿justa causa alegada por el empleador? (Art. 62 CST)
3. Indemnización: ¿cuál aplica según Art. 64 CST?
4. Si hay fuero: ¿sindical, maternidad, reforzado?

Citas del corpus V1.1 que típicamente aplican:
- Constitución Política de 1991, art. 25 (trabajo como derecho)
- Constitución Política de 1991, art. 13 (igualdad)
- Ley 100 de 1993, art. 1 (seguridad social)

## Etapa 3 · EJECUTANDO (drafting)

Documentos a redactar:
1. Poder judicial (formato estándar del despacho)
2. Demanda ordinaria laboral con:
   - Hechos numerados (máximo 10)
   - Fundamentos de derecho (cite Constitución + Ley)
   - Pretensiones (subordinadas y principales)
   - Anexos (lista completa)
3. Anexos: certificados, comunicaciones, historia laboral

## Etapa 4 · BORRADOR-FINAL (review)

REVIEW-AGENT debe verificar:
- ¿Cita normas correctas del corpus V1.1?
- ¿Pretensiones proporcionales a los hechos?
- ¿Plazo procesal cumplido (tutela 10 días hábiles, demanda ordinaria)?
- ¿Juzgado competente (Laboral del Circuito para demandas > 20 SMLV)?

## Etapa 5 · EN-ESPERA-DE-APROBACIÓN (approval gate)

`minimum_human_signoff: 1` por abogado del área laboral.
Si la indemnización reclamada supera 100 SMLV → requiere socio (socio + abogado = 2 firmas).

## Etapa 6 · LISTO-PARA-CLIENTE y FIRMADO-Y-ENTREGADO

- Revisión con cliente de pretensiones y cuantía
- Radicación ante juzgado laboral competente
- Cargo de radicación archivado en `data/matters/<id>/filings/`

## Red flags críticas

1. **Liquidación firmada sin asesoría**: Si el cliente firmó liquidación
   definitiva al momento del retiro, evaluar vicio del consentimiento
   (error esencial en consentimiento). Documentar estado de
   conocimiento al momento de firma.

2. **Prescripción probable (> 3 años)**: Verificar fecha exacta del
   hecho generador. Acciones changosas prescriben a los 3 años (Art.
   151 CST). Algunas a 1 año. Documentar cutoff.

3. **Cliente servidor público**: Va a jurisdicción contencioso-
   administrativa, NO laboral ordinaria. Cambiar playbook a
   `administrativo.md`.

4. **Convención colectiva aplicable**: Si hay convención, fuero
   sindical puede aplicar (Art. 112 CST). Demanda requiere permiso
   del juez laboral para despedir (acción de fuero previa).

5. **Despido por denuncia sindical**: Tutela + acción de reintegro
   simultáneas. Documentar evidencia de la denuncia previa.
