---
practice_area: constitucional
typical_matter_types:
  - accion_de_tutela_salud
  - accion_de_tutela_educacion
  - accion_de_tutela_debido_proceso
  - accion_de_tutela_libre_desarrollo_personalidad
  - accion_de_tutela_derecho_peticion
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
  - poder_especial_tutela.docx
  - accion_de_tutela.docx
  - historia_clinica.pdf
  - negacion_EPS_comunicacion.pdf
  - concepto_medico_tratante.pdf
  - carnets_EPS_y_documentos_identidad.pdf
deadline_types:
  - tutela_presentacion
  - demanda_contestacion
  - impugnacion_sentencia
  - consulta_jerarquica
citation_corpus:
  - Constitución Política de 1991
  - Ley 100 de 1993
red_flags:
  - Si hay más de 1 año desde la negación → duda sobre inmediatez
  - Si cliente es menor → representación legal obligatoria
  - Si hay proceso ordinario paralelo → evaluar subsidiariedad
  - Si cuantía supera 50 SMLV → no aplica tutela (excluida por cuantía)
---

# Playbook Constitucional (Tutela)

Role: Guía para DRAFTING-AGENT y REVIEW-AGENT en acciones de tutela
colombianas (Decreto 2591 de 1991).

## Etapa 1 · INTAKE

Datos críticos:
- Derecho fundamental vulnerado (salud, educación, debido proceso,
  libre desarrollo, petición, etc.)
- Hecho vulnerador (acción u omisión) con fecha exacta
- Autoridad pública o particular con régimen de tutela
- Pretensión específica (entrega de medicamento, cita médica, etc.)
- Documentación de la negación (comunicación de EPS, acto administrativo)

## Etapa 2 · PLANEACIÓN (research)

Cuestiones:
1. **Inmediatez**: ¿Hecho vulnerador ocurrió en términos razonables?
   Regla general: < 1 año. Jurisprudencia flexibiliza.
2. **Subsidiariedad**: ¿Hay otros medios de defensa judicial? Si sí, ¿son
   expeditos y eficaces? (Si no, tutela procede.)
3. **Causales de improcedencia**:Hechos superados, conexidad con otro
   proceso, cuantía > 50 SMLV (excluida por cuantía).
4. **Causal de tutela**: Aplicar categorías jurisprudenciales.

Citas del corpus V1.1:
- Constitución Política de 1991, art. 13 (igualdad — base de muchas tutelas)
- Constitución Política de 1991, art. 29 (debido proceso)
- Ley 100 de 1993, art. 1 (seguridad social — para tutelas de salud)
- Ley 100 de 1993, art. 2 (principios de eficiencia, universalidad, solidaridad)
- Ley 100 de 1993, art. 3 (derecho a la seguridad social)

## Etapa 3 · EJECUTANDO (drafting)

Estructura de la tutela (Art. 14 Decreto 2591/1991):
1. Nombre y domicilio del accionante
2. Nombre y domicilio del accionado
3. Derecho vulnerado o amenazado
4. Hechos que motivan la acción
5. Acción u omisión que motivó la vulneración
6. Pretensión
7. Documentos relevantes
8. Declaración bajo la gravedad del juramento

## Etapa 4 · BORRADOR-FINAL (review)

REVIEW-AGENT:
- ¿Cita Constitución + Ley 100 correctamente del corpus V1.1?
- ¿Identifica derecho fundamental específico?
- ¿Tutela cumple con requisitos del Art. 14 Decreto 2591?
- ¿Pretensión es clara y específica?
- ¿Hay inmediatez razonable?
- ¿Subsidiariedad analizada?

## Etapa 5 · EN-ESPERA-DE-APROBACIÓN (approval gate)

`minimum_human_signoff: 1` por abogado constitucional.
Si la tutela es de cuidado intensivo o end-of-life → requiere socio.

## Etapa 6 · Radicación

Radicar ante juez competente:
- Civil Municipal (regla general)
- Administrativo Municipal (contra autoridad pública)
- Juez de Control de Garantías (penal)

Tutela se radica físico. El juez debe fallar en 10 días hábiles.

## Red flags críticas

1. **Más de 1 año desde la negación**: Duda sobre inmediatez. Jurisprudencia
   acepta casos excepcionales (enfermedades crónicas, etc.). Documentar
   por qué se considera razonable.

2. **Cliente menor**: Representación legal obligatoria por padres/tutores.
   Si los padres no pueden, defensor de familia.

3. **Proceso ordinario paralelo**: Evaluar subsidiariedad. Si hay otro
   medio expedito y eficaz, tutela NO procede (regla general).

4. **Cuantía supera 50 SMLV**: Tutela excluida por cuantía (Art. 30
   Decreto 2591). Cambiar a proceso ordinario civil.
