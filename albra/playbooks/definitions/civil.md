---
practice_area: civil
typical_matter_types:
  - demanda_civil_extracontractual
  - demanda_civil_contractual
  - accion_reivindicatoria
  - accion_rescision
  - sucesion_testamentaria
  - sucesion_intestada
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
  - certificado_runt_propiedad_vehicular.pdf
  - certificado_tradicion_libertad.pdf
  - contrato_relevante.pdf
  - facturas_y_comprobantes.pdf
deadline_types:
  - prescripcion_civil_extracontractual
  - prescripcion_civil_contractual
  - prescripcion_civil_accion_cambio
  - demanda_contestacion
  - recursos_sentencia
citation_corpus:
  - Constitución Política de 1991
  - Ley 80 de 1993
red_flags:
  - Si la prescripción está por vencer → actuar en 30 días máx
  - Si hay menores involucrados → curador adjunto obligatorio
  - Si hay proceso penal paralelo → esperar sentencia penal (prejudicialidad)
  - Si cuantía supera 500 SMLV → juzgado civil del circuito
---

# Playbook Civil

Role: Guía para DRAFTING-AGENT y REVIEW-AGENT en matters civiles.
Cubre responsabilidad civil extracontractual (Art. 2341 C.C.), contractual,
acciones reivindicatorias, rescisión, sucesiones.

## Etapa 1 · INTAKE

Datos críticos:
- Hechos generadores con fechas exactas (para prescripción)
- Cuantía de la pretensión (define competencia)
- Partes (demandante, demandado, terceros)
- Documentos: contratos, facturas, comprobantes, registros públicos

## Etapa 2 · PLANEACIÓN (research)

Cuestiones jurídicas:
1. **Prescripción**: revisar tipo
   - Extracontractual: 20 años desde el hecho (Art. 2536 C.C.)
   - Contractual ordinaria: 10 años (Art. 2512 C.C.)
   - Acciones redhibitorias: 1 año
2. **Cuantía**: define competencia (Civil Municipal < 40 SMLV, Civil del Circuito >)
3. **Jurisdicción**: ordinaria civil vs. contencioso-administrativa vs. familia

Citas del corpus V1.1 que típicamente aplican:
- Constitución Política de 1991, art. 29 (debido proceso)
- Ley 80 de 1993, art. 1 (contratos estatales — si aplica a entidad pública)

## Etapa 3 · EJECUTANDO (drafting)

Documentos:
1. Poder judicial
2. Demanda civil con:
   - Hechos numerados (máximo 15)
   - Fundamentos de derecho (cite Constitución + Código Civil)
   - Pretensiones (subordinadas y principales)
   - Cuantía estimada
   - Anexos

## Etapa 4 · BORRADOR-FINAL (review)

REVIEW-AGENT:
- ¿Normas citadas del corpus V1.1?
- ¿Cuantía correcta para competencia?
- ¿Término de prescripción respetado?
- ¿Juzgado competente (Civil Municipal < 40 SMLV; Civil del Circuito >= 40 SMLV)?

## Etapa 5 · EN-ESPERA-DE-APROBACIÓN (approval gate)

`minimum_human_signoff: 1` por abogado civil.
Si cuantía supera 500 SMLV → requiere socio (socio + abogado = 2 firmas).

## Etapa 6 · Radicación

Radicar ante juzgado civil competente según cuantía. Conservar copia con
cargo en `data/matters/<id>/filings/`.

## Red flags críticas

1. **Prescripción por vencer**: Si faltan < 30 días para prescripción,
   presentar demanda inmediatamente con reserva de ampliación de hechos.

2. **Menores involucrados**: Curador adjunto obligatorio. Designación
   por defensor de familia (ICBF).

3. **Proceso penal paralelo**: Prejudicialidad civil vs penal. El juez
   civil debe suspender hasta sentencia penal firme.

4. **Cuantía alta (> 500 SMLV)**: Juzgado Civil del Circuito. Requiere
   2 firmas (abogado + socio) en approval chain.
