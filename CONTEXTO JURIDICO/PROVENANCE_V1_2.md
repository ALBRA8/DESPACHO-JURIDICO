# Corpus V1.2 — Evidencia de Provenance y Auditoría

> Documento de auditoría: fuente → captura → hash → transformación → artículo → corpus → retrieval/citation.
> Fecha: 2026-10-28
> HEAD remoto: `392f416` (published, CI VERIFIED)

## Estado

**Corpus V1.2 = VERIFIED WITH LIMITATIONS**

- El corpus está publicado en GitHub (commit `81a9c83`, pushed).
- Los tests pasan en CI (1071 passed, 8 skipped en 3.10/3.11/3.12).
- La ingesta Playwright fue demostrada localmente.
- PERO no se conserva ni hashea el HTML crudo de origen.

## Auditoría de trazabilidad source→byte

### Matriz por documento

| Documento | source_url | captured_bytes | captured_hash | extracted_article | stored_article | stored_hash | source→byte provenance |
|---|---|---|---|---|---|---|---|
| Constitución 1991 | `http://www.secretariasenado.gov.co/senado/basedoc/constitucion_politica_1991.htm` | NOT STORED | NOT STORED | 32 articles | 32 articles | `d6c378a7...` (SHA-256 de texto reconstruido) | NOT VERIFIED |
| Ley 100 de 1993 | `http://www.secretariasenado.gov.co/senado/basedoc/ley_0100_1993.html` | NOT STORED | NOT STORED | 45 articles | 45 articles | `5cb5eba3...` (SHA-256 de texto reconstruido) | NOT VERIFIED |
| Ley 80 de 1993 | `http://www.secretariasenado.gov.co/senado/basedoc/ley_0080_1993.html` | NOT STORED | NOT STORED | 48 articles | 48 articles | `5aa5112f...` (SHA-256 de texto reconstruido) | NOT VERIFIED |

### Qué significa cada columna

- **source_url**: URL de la fuente oficial. VERIFIED (documentada en `source_url` field de cada doc).
- **captured_bytes**: HTML crudo capturado por Playwright. NOT STORED — el HTML se procesó en una ejecución one-shot de Playwright y se descartó. Solo se conservaron los articles extraídos.
- **captured_hash**: Hash del HTML crudo. NOT STORED — no existe.
- **extracted_article**: Articles extraídos con regex `ARTICULO N.`. VERIFIED (almacenados en `articles` list de cada doc).
- **stored_article**: Mismo que extracted. VERIFIED.
- **stored_hash**: SHA-256 del `raw_content` (texto reconstruido `"ARTICULO N. <text>"` concatenado). VERIFIED (hash declarado == hash computado). PERO el hash corresponde al texto reconstruido, NO al HTML fuente.

### Verificación de hash (ejecutada localmente)

```
Constitución 1991:
  declared: d6c378a743f896c0184a595b00cb51d66153a56ec9a5953a8220cf2699de0f22
  computed: d6c378a743f896c0184a595b00cb51d66153a56ec9a5953a8220cf2699de0f22
  match: True
  raw_content type: bytes
  raw_content size: 6643 bytes
  raw_content starts with HTML: False
  raw_content starts with ARTICULO: True

Ley 100 de 1993:
  declared: 5cb5eba301f248ae80bf0106168e95a4f1ba97da78ffe596d4517ad3f6770e9f
  computed: 5cb5eba301f248ae80bf0106168e95a4f1ba97da78ffe596d4517ad3f6770e9f
  match: True
  raw_content type: bytes
  raw_content size: 16631 bytes
  raw_content starts with HTML: False
  raw_content starts with ARTICULO: True

Ley 80 de 1993:
  declared: 5aa5112f87637fb0179ecb4ba216be713ffa35a3f3be78d0e7262175bf05cbbf
  computed: 5aa5112f87637fb0179ecb4ba216be713ffa35a3f3be78d0e7262175bf05cbbf
  match: True
  raw_content type: bytes
  raw_content size: 15880 bytes
  raw_content starts with HTML: False
  raw_content starts with ARTICULO: True
```

## Limitación explícita (no oculta)

**`raw_content` es texto reconstruido y el hash actual corresponde al texto almacenado, no al HTML crudo capturado.**

Esto significa:

1. ✓ Si alguien modifica un article en el código → el hash no coincide → detectable.
2. ✗ NO garantiza que el texto almacenado coincide byte-a-byte con el HTML de la fuente oficial.
3. ✗ NO se conserva el HTML crudo capturado por Playwright.
4. ✗ NO existe un hash del HTML fuente.
5. ✗ source→byte provenance = NOT VERIFIED.

## Cadena de transformación documentada

```
fuente oficial (secretariasenado.gov.co)
    → Playwright fetch (HTML renderizado, ~80KB para Constitución)
    → regex ARTICULO N. (patrón case-insensitive, accent-aware)
    → cleanup: strip HTML tags + normalize whitespace + strip prefix "o."
    → article {number: str, text: str}
    → concatenar "ARTICULO N. text" para construir raw_content
    → content_hash = SHA-256(raw_content)
    → real_corpus_v12.py (published en GitHub, commit 81a9c83)
    → CitationAuditor(corpus_version='v12') indexa 125 articles
    → CitationGraph.index_corpus_v12() (si se invoca)
```

**Gap en la cadena**: entre "Playwright fetch (HTML renderizado)" y "regex ARTICULO N." — el HTML crudo se descarta. No se conserva ni su hash.

## Tests negativos de integridad (ejecutados localmente)

1. **Tampering de article text**: Si se modifica el texto de un artículo, `content_hash` (SHA-256 del raw_content) no coincidirá → detectable.
2. **Cita inventada** (art 999): CitationAuditor → BLOCKED (art no en corpus).
3. **Sentencia rechazada** (C-251/2002): CitationAuditor → BLOCKED (rechazada honestamente).
4. **Quote mismatch**: CitationAuditor → BLOCKED si la quote literal no aparece en el texto fuente.

## Conclusión

- Corpus V1.2 published en GitHub: VERIFIED
- Tests pasando en CI: VERIFIED
- Ingesta Playwright demostrada localmente: VERIFIED (localmente)
- source→byte provenance: NOT VERIFIED (HTML crudo no conservado)
- Estado final: **VERIFIED WITH LIMITATIONS**
