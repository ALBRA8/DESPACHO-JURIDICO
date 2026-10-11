# Knowledge Layer Colombia - VACÍO POR DISEÑO

Esta capa está PREPARADA para carga controlada de conocimiento jurídico colombiano
pero NO contiene contenido todavía.

## Estructura (V1.6 - ready to learn)

```
colombia/
├── constitution/       # Constitución Política 1991
├── legislation/        # Leyes, decretos, ordenanzas
├── jurisprudence/      # Sentencias, autos, providencias
├── regulations/        # Reglamentos, resoluciones
├── doctrine/           # Doctrina jurídica
├── administrative/    # Actos administrativos
└── procedural/        # Códigos de procedimiento
```

## Carga controlada (FASE 2 - posterior)

Cada item de conocimiento debe traer:
- `kind`: constitution | law | decree | sentence | etc.
- `jurisdiction`: CO
- `source`: URL oficial
- `source_type`: official
- `effective_from`: fecha
- `effective_to`: null si vigente
- `version`: versión
- `text`: contenido
- `articles`: lista de artículos (si aplica)
- `metadata`: extra
- `hash`: SHA-256 del contenido
- `provenance`: SOURCE → INGESTION → EXTRACTION → EVIDENCE

## Reglas

- NUNCA inventar contenido jurídico
- Toda carga requiere HITL (capability `knowledge_load`)
- Solo fuentes oficiales verificables
- Trazabilidad obligatoria
