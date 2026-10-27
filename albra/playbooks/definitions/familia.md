---
practice_area: familia
typical_matter_types:
  - divorcio_contencioso
  - sucesion_familia
  - custodia_menores
  - alimentos
  - regulacion_visitas
  - paternidad_reconocimiento
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
  - poder_judicial_familia.docx
  - demanda.docx
  - registro_civil_matrimonio.pdf
  - registros_civiles_hijos.pdf
  - certificado_renta_y_patrimonio.pdf
  - icbf_concepto_si_menores.pdf
deadline_types:
  - prescripcion_civil_extracontractual
  - demanda_contestacion
  - recursos_sentencia
citation_corpus:
  - Constitución Política de 1991
red_flags:
  - Si hay violencia intrafamiliar → medidas cautelares previas obligatorias
  - Si hay menores → ICBF debe intervenir como curador adjunto
  - Si cuantía supera 40 SMLV → juzgado de familia del circuito
  - Si hay bienes sociales complejos → avalúo comercial previo
---

# Playbook Familia

Role: Guía para DRAFTING-AGENT y REVIEW-AGENT en matters de familia
colombiana. Cubre divorcio contencioso, custodia, alimentos, regulación
de visitas, sucesión familiar.

## Etapa 1 · INTAKE

Datos críticos:
- Estado civil del cliente (casado, unión marital de hecho, soltero)
- Hijos menores (nombres, edades, registros civiles)
- Patrimonio común o separado (bienes sociales, propios)
- Ingresos de ambas partes (para alimentos)
- ¿Violencia intrafamiliar previa o actual?

## Etapa 2 · PLANEACIÓN (research)

Cuestiones:
1. **Competencia**: Juzgado de Familia (Ley 640 de 2001).
   - Municipal: cuantía < 40 SMLV
   - Circuito: cuantía >= 40 SMLV
2. **Mediación obligatoria** (Ley 640): Antes de demanda, audiencia
   de conciliación en Centro de Conciliación.
3. **Menores**: ICBF como curador adjunto (Art. 31 Ley 1098 de 2006).
4. **Causales de divorcio** (Art. 6 Ley 25 de 1992): adulterio,
   sevicia, injuria, embriaguez habitual, etc.

Citas del corpus V1.1:
- Constitución Política de 1991, art. 5 (familia como célula básica)
- Constitución Política de 1991, art. 13 (igualdad — para alimentos)

## Etapa 3 · EJECUTANDO (drafting)

Documentos:
1. Poder judicial de familia
2. Demanda con:
   - Hechos numerados
   - Causal invocada (para divorcio) o pretensión específica
   - Cuantía (si aplica)
   - Anexos: registro civil matrimonio, hijos, certificado renta
3. Solicitud de audiencia de conciliación previa (si aplica)

## Etapa 4 · BORRADOR-FINAL (review)

REVIEW-AGENT:
- ¿Cita Constitución art. 5 correctamente del corpus V1.1?
- ¿Mediación previa agotada (cuando obligatoria)?
- ¿ICBF convocado si hay menores?
- ¿Cuantía correcta para competencia?
- ¿Bienes sociales correctamente identificados?

## Etapa 5 · EN-ESPERA-DE-APROBACIÓN (approval gate)

`minimum_human_signoff: 1` por abogado de familia.
Si cuantía supera 200 SMLV → requiere socio (socio + abogado = 2 firmas).

## Etapa 6 · Radicación

Radicar ante Juzgado de Familia competente por cuantía. Conciliación
previa ante Centro de Conciliación (Ley 640).

## Red flags críticas

1. **Violencia intrafamiliar previa o actual**: Medidas cautelares
   previas obligatorias. Solicitar ante juez de familia: protección,
   alejamiento, exclusión del hogar. Documentar evidencia (denuncia
   previa, examen médico legal).

2. **Menores involucrados**: ICBF debe intervenir como curador
   adjunto (Art. 31 Ley 1098 de 2006). Sin citación a ICBF, proceso
   nulo.

3. **Bienes sociales complejos**: Avalúo comercial previo obligatorio
   para bienes inmuebles. Documentar avalúos con perito idóneo.

4. **Pensión de alimentos**: Tabla de alimentos según ingresos del
   alimentante y necesidades del alimentario. Mínimo legal: 1 SMLV.
