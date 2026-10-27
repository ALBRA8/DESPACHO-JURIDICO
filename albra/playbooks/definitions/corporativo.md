---
practice_area: corporativo
typical_matter_types:
  - contratos_comerciales
  - constitucion_sociedad
  - reforma_estatutos
  - fusion_adquisicion
  - contratos_estatales_ley_80
  - compliance_governance
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
  - certificado_camara_comercio.pdf
  - estatutos_sociales.pdf
  - acta_junta_directiva.pdf
  - contrato_relevante.docx
  - due_diligence_checklist.xlsx
  - poder_representacion_legal.docx
deadline_types:
  - prescripcion_civil_contractual
  - prescripcion_civil_extracontractual
citation_corpus:
  - Constitución Política de 1991
  - Ley 80 de 1993
red_flags:
  - Si hay conflicto de interés → ethical wall obligatorio
  - Si contrato estatal → aplicar Ley 80 (no Código Civil)
  - Si hay datos personales → Ley 1581 compliance
  - Si fusión supera USD 1M → notificación a SuperSociedades
---

# Playbook Corporativo

Role: Guía para DRAFTING-AGENT y REVIEW-AGENT en matters corporativos
colombianos. Cubre contratos comerciales, constitución de sociedades,
reformas estatutarias, M&A, contratos estatales (Ley 80), compliance.

## Etapa 1 · INTAKE

Datos críticos:
- Cliente: sociedad (NIT, razón social, representante legal)
- Operación: contrato / reforma / fusión / due diligence / compliance
- Partes involucradas (incluye accionistas/junta directiva)
- Cuantía / valor del negocio
- Plazo del contrato (si aplica)

## Etapa 2 · PLANEACIÓN (research)

Cuestiones:
1. **Naturaleza del contrato**: ¿civil, comercial, estatal (Ley 80)?
2. **Capacidad de las partes**: representación legal vigente (cámara
   de comercio).
3. **Licencias y permisos**: ¿requiere registro ante autoridad?
4. **Conflicto de interés**: ¿abogado del despacho tiene relación con
   la contraparte?
5. **Datos personales**: ¿maneja datos sensibles? (Ley 1581 de 2012)

Citas del corpus V1.1:
- Constitución Política de 1991, art. 29 (debido proceso contractual)
- Ley 80 de 1993, art. 1 (objeto del contrato estatal)
- Ley 80 de 1993, art. 2 (entidades estatales)
- Ley 80 de 1993, art. 24 (principio de transparencia en contratación estatal)

## Etapa 3 · EJECUTANDO (drafting)

Documentos:
1. Contrato / acta / poder según operación:
   - **Contrato comercial**: cláusulas (objeto, precio, plazo, garantías,
     indemnidades, jurisdicción, ley aplicable)
   - **Reforma estatutaria**: acta de junta, modificación registro cámara
   - **Fusión**: protocolo, acuerdos accionarios, avalúos
2. Anexos: certificados cámara, RUT, RIT, estatutos, poderes

## Etapa 4 · BORRADOR-FINAL (review)

REVIEW-AGENT:
- ¿Contradicciones entre cláusulas? → usar ContradictionGuard
- ¿Jurisdicción correcta (colombiana vs extranjera)?
- ¿Moneda y forma de pago claras?
- ¿Plazo y causales de terminación explícitas?
- ¿Para contratos estatales: principio de transparencia (Art. 24 Ley 80)?
- ¿Cláusulas de confidencialidad, no competencia, propiedad intelectual?

## Etapa 5 · EN-ESPERA-DE-APROBACIÓN (approval gate)

`minimum_human_signoff` según valor:
- < 100 SMLV: 1 firma (abogado corporativo)
- 100-500 SMLV: 1 firma socio
- > 500 SMLV: 2 firmas (socio + abogado)
- Contratos estatales > 1000 SMLV: socio + compliance officer

## Etapa 6 · Cierre y firma

- Revisión con cliente (CEO/junta directiva)
- Firma ante notario si requiere escritura pública (constitución,
  reforma estatutaria, compraventa inmueble)
- Registro en cámara de comercio o SuperSociedades según caso

## Red flags críticas

1. **Conflicto de interés**: Si el despacho ya asesora a la contraparte
   o tiene relación con accionista, configurar **ethical wall**
   (RBAC + matter-level access lists, V2.1+).

2. **Contrato estatal**: Aplica Ley 80 de 1993, NO Código Civil.
   Diferencias clave: principio de transparencia (Art. 24), selección
   por licitación/concurso o contratación directa, límites de adiciones.

3. **Datos personales (Ley 1581)**: Si el contrato involucra manejo
   de datos personales, cláusula de protección de datos obligatoria.
   Encargado vs responsable. Notificación a Superintendencia.

4. **Fusión > USD 1M**: Notificación previa a Superintendencia de
   Sociedades. Plazo de 30 días para objeción. Sin notificación, nulidad.
