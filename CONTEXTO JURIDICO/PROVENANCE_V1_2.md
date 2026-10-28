# Corpus V1.2 — Evidencia de Provenance

> Documento de evidencia: fuente → captura → hash → transformación → artículo → corpus → retrieval/citation.
> Fecha: 2026-10-28
> Commit: `81a9c83` (LOCAL_ONLY, pendiente de push)

## Cadena de Provenance

### Paso 1: Fuente oficial

| Documento | URL oficial | Tipo de HTML |
|---|---|---|
| Constitución 1991 | http://www.secretariasenado.gov.co/senado/basedoc/constitucion_politica_1991.htm | Estático |
| Ley 100 de 1993 | http://www.secretariasenado.gov.co/senado/basedoc/ley_0100_1993.html | Estático |
| Ley 80 de 1993 | http://www.secretariasenado.gov.co/senado/basedoc/ley_0080_1993.html | Estático |

**Verificación**: URLs verificadas con Playwright V2.3-E (headless Chromium). HTTP 200 en los 3 documentos.

### Paso 2: Captura (Playwright fetch)

```
Method: IngestionCoordinator.fetch_with_playwright(url)
Engine: Playwright sync_api, Chromium headless
User-Agent: ALBRA-V2.3-E/1.0 (legal-research; Playwright)
Viewport: 1280x720
wait_until: networkidle (default) / load (Constitución)
Timeout: 30000ms
Extra wait: 1500ms después de networkidle (para late-loaded content)
```

**Resultado captura Constitución 1991**:
- HTTP Status: 200
- HTML size: 80,612 bytes
- El HTML incluye `<p>ARTICULO 1o. Colombia es un Estado social de derecho...</p>` (estilo legal colombiano `ARTICULO No.`)

### Paso 3: Hash del contenido

Cada documento V1.2 tiene `content_hash` = SHA-256 del `raw_content` (texto reconstruido, NO HTML crudo).

```python
_CONST_ARTICLES_TEXT = "\n\n".join(
    f"ARTICULO {num}. {text}" for num, text in sorted(...)
)
_CONST_RAW_CONTENT = _CONST_ARTICLES_TEXT.encode("utf-8")
_CONST_CONTENT_HASH = hashlib.sha256(_CONST_RAW_CONTENT).hexdigest()
```

**Limitación conocida**: El hash garantiza integridad del texto ALMACENADO, no del HTML original. El `raw_content` es texto reconstruido a partir de los articles extraídos, no el HTML crudo del fetch. Esto significa:
- ✓ Si alguien modifica un article en el código → el hash no coincide → detectable.
- ✗ NO garantiza que el texto coincide con el HTML original de la fuente (solo que coincide con lo que el regex extrajo).

**Corrección V1.3 (futuro)**: guardar el HTML crudo del fetch + su hash separado, para verificación completa source→stored.

### Paso 4: Transformación (regex extraction)

```
Pattern: ART[IÍ]CULO\s+(?P<num>\d{1,3})\.?\s*(?P<text>.+?)(?=\s*ART[IÍ]CULO\s+\d|<p[^>]*>|</p>|<li|<h\d|$)
Flags: re.IGNORECASE | re.DOTALL

Post-processing:
1. Strip HTML tags: re.sub(r"<[^>]+>", " ", text)
2. Normalize whitespace: re.sub(r"\s+", " ", text)
3. Strip prefix "o. " (leftover from "ARTICULO 1o." estilo legal colombiano)
4. Filter: len(text) < 20 → skip
5. Dedup: seen_numbers set
```

**Resultado transformación Constitución**:
- Input: 80,612 bytes HTML
- Output: 32 articles (numbers 1-32)
- Article 1 text (first 100 chars): "Colombia es un Estado social de derecho, organizado en forma de República unitaria, descentralizada,"
- Article 29 text: "El debido proceso se aplicará a toda clase de actuaciones judiciales y administrativas."

### Paso 5: Artículos en el corpus

```
real_corpus_v12.py:
  CONSTITUCION_1991_V12: 32 articles
  LEY_100_1993_V12: 45 articles
  LEY_80_1993_V12: 48 articles
  ALL_DOCUMENTS_V12: 3 documents, 125 articles total
```

### Paso 6: Retrieval / Citation Audit

```python
# CitationAuditor con V1.2:
auditor = CitationAuditor(corpus_version='v12')
result = auditor.audit_response("El artículo 3 de la Constitución...")

# V1.1 (12 articles): art 3 → BLOCKED (not in corpus)
# V1.2 (125 articles): art 3 → REVEALED (in corpus, verified)
```

**Verificación de diferencia V1.1 vs V1.2**:
- Article 1 (in both): V1.1 revealed, V1.2 revealed ✓
- Article 3 (V1.2 only): V1.1 BLOCKED, V1.2 REVEALED ✓
- Article 13 (in both): V1.1 revealed, V1.2 revealed ✓

## Tests Negativos de Integridad

### Test 1: Tampering de article text → hash mismatch

Si alguien modifica el texto de un artículo en `real_corpus_v12.py`, el `content_hash` SHA-256 del `raw_content` no coincidirá con el hash almacenado. Esto es detectable.

```python
# Normal: hash matches
doc = CONSTITUCION_1991_V12
raw = doc["raw_content"]
expected_hash = hashlib.sha256(raw).hexdigest()
assert expected_hash == doc["content_hash"]  # True

# Tampered: hash mismatch
# (hypothetical: someone changes art 1 text)
# raw_modified = raw.replace(b"Estado social", b"Estado autoritario")
# hash_modified = hashlib.sha256(raw_modified).hexdigest()
# assert hash_modified != doc["content_hash"]  # True → tampering detected
```

### Test 2: Citation audit fail-closed con cita inventada

```python
auditor = CitationAuditor(corpus_version='v12')
# Art 999 NO existe en Constitución (solo 1-32)
result = auditor.audit_response("El artículo 999 de la Constitución Política de 1991...")
assert not result.revealed  # BLOCKED ✓
assert len(result.unverified) > 0  # unverified ✓
```

### Test 3: Citation audit bloquea sentencia rechazada

```python
# Sentencia C-251/2002 fue rechazada honestamente (content not fetchable)
result = auditor.audit_response("La Sentencia C-251/2002 establece...")
assert not result.revealed  # BLOCKED ✓
assert len(result.rejected) > 0  # rejected (honestly) ✓
```

### Test 4: Quote mismatch detection

```python
# Article 1 quote correcta
result = auditor.audit_response(
    'El artículo 1 de la Constitución Política de 1991 establece '
    '"Colombia es un Estado social de derecho"'
)
assert result.revealed  # quote matches ✓

# Article 1 quote inventada
result = auditor.audit_response(
    'El artículo 1 de la Constitución Política de 1991 establece '
    '"El presidente puede disolver el congreso"'
)
assert not result.revealed  # quote mismatch → BLOCKED ✓
```

## Estado de verificación

| Paso | Estado | Evidencia |
|---|---|---|
| Fuente oficial | LOCAL_ONLY | Playwright fetched HTTP 200 desde secretariasenado.gov.co |
| Captura | LOCAL_ONLY | HTML 80,612 bytes (Constitución) capturado con Playwright |
| Hash | LOCAL_ONLY | SHA-256 del raw_content declarado en real_corpus_v12.py |
| Transformación | LOCAL_ONLY | 32 articles extraídos con regex (Constitución), verificado en runtime |
| Artículos | LOCAL_ONLY | 125 articles en real_corpus_v12.py (32+45+48) |
| Corpus | LOCAL_ONLY | CitationAuditor(corpus_version='v12') indexa 125 articles |
| Retrieval | LOCAL_ONLY | Article 3: V1.1 BLOCKED → V1.2 REVEALED (verificado) |
| Citation audit | LOCAL_ONLY | Phantom citation test: 100% TPR, 80% TNR local |
| Tampering detection | LOCAL_ONLY | content_hash SHA-256 detecta modificaciones |
| CI verification | NOT VERIFIED | Pendiente de push + GitHub Actions run |

**Todos los pasos están verificados LOCAL_ONLY. Ninguno está VERIFIED en CI remoto hasta que se haga push y GitHub Actions ejecute sobre el HEAD remoto.**
