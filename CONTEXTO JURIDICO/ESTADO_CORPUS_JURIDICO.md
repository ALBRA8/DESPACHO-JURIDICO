# ESTADO DEL CORPUS JURÍDICO

- **Estado:** `PARTIAL`
- **Jurisdicción inicial declarada:** Colombia
- **Última revisión documental:** 2026-10-25

## 1. Principio obligatorio

El corpus debe contener fuentes identificables, contenido real recuperado de la fuente, procedencia trazable y transformaciones documentadas. Un resumen, una etiqueta o una reconstrucción generada no debe almacenarse ni presentarse como texto oficial. Si una fuente no se puede recuperar o validar, se registra la limitación y se abstiene de inventar.

## 2. Fallos históricos del piloto V1.0

Según `docs/CORPUS_PILOT_AUDIT_V1_1.md`, el piloto V1.0 contenía problemas graves: artículos constitucionales reconstruidos o mal emparejados, textos resumidos presentados como oficiales, caracterización incorrecta de C-251/2002, ratio decidendi fabricado para T-760/2008 y registros sintéticos de jurisprudencia extranjera y doctrina.

El mismo informe registra que el material no recuperable o sintético se eliminó o rechazó para V1.1. Esta es una síntesis del informe fuente, no una nueva inspección de todos los datos del repositorio.

## 3. Cobertura que V1.1 declara

El informe `docs/CORPUS_PILOT_AUDIT_V1_1.md` declara:

| Fuente | Cobertura declarada | Fuente primaria indicada |
|---|---|---|
| Constitución Política de Colombia de 1991 | Arts. 1, 2, 5, 13, 25 y 29 | Senado de la República |
| Ley 100 de 1993 | Arts. 1, 2 y 3 | Senado de la República |
| Ley 80 de 1993 | Arts. 1, 2 y 24 | Senado de la República |

El informe indica un total de tres documentos y doce artículos, transformados de HTML a texto plano, con hashes SHA-256 registrados parcialmente. También declara que no se incorporó jurisprudencia real, doctrina ni documento extranjero, y que `source_url_authenticated=False`.

**Advertencia:** esta tabla refleja la cobertura declarada por el informe. La revisión actual no recalculó los hashes ni comparó cada fragmento con el contenido vigente de las fuentes oficiales.

## 4. Fuentes indicadas por el informe V1.1

- Constitución de 1991: http://www.secretariasenado.gov.co/senado/basedoc/constitucion_politica_1991.htm
- Ley 100 de 1993: http://www.secretariasenado.gov.co/senado/basedoc/ley_0100_1993.html
- Ley 80 de 1993: http://www.secretariasenado.gov.co/senado/basedoc/ley_0080_1993.html

La presencia de una URL no demuestra por sí sola que el contenido guardado coincida con la fuente, que la URL siga accesible o que se haya validado criptográficamente.

## 5. Gaps conocidos

- Corpus pequeño: solo tres documentos normativos según el informe.
- Sin jurisprudencia incorporada en el piloto V1.1.
- Sin doctrina incorporada.
- Sin documento extranjero.
- Sin autenticación criptográfica declarada de las fuentes.
- La cobertura del corpus en el HEAD actual debe comprobarse directamente, sin asumir que coincide con el informe histórico.
- Los posibles cambios legislativos posteriores deben evaluarse con vigencia temporal y fuente oficial; no inferir vigencia por ausencia de una fecha de derogación.

## 6. Criterios de aceptación de cada nuevo documento

1. Identidad del documento y jurisdicción correctas.
2. URL o localizador de fuente primaria registrado.
3. Contenido original recuperado y preservado de forma trazable.
4. Transformación documentada (por ejemplo, HTML a texto), sin ocultar pérdida de estructura.
5. Hash calculado sobre una representación claramente definida.
6. Artículos y metadatos vinculados al documento correcto.
7. Estado temporal respaldado por evidencia; distinguir fecha de publicación, entrada en vigor, modificación, suspensión y derogación cuando aplique.
8. Fuente, contenido y transformaciones reproducibles o sus limitaciones declaradas.
9. Pruebas de integridad, artículos inexistentes, conflicto y abstención.
10. Ningún contenido sintético presentado como fuente primaria.

## 7. Fuentes originales

- [Informe de auditoría del piloto V1.0](../docs/CORPUS_PILOT_AUDIT_V1.md)
- [Informe de auditoría del piloto V1.1](../docs/CORPUS_PILOT_AUDIT_V1_1.md)
- [Auditoría final pre-corpus](../docs/AUDIT_FINAL_PRECORPUS.md)
