# DESPACHO JURÍDICO — ESTADO ACTUAL

- **Estado del documento:** `PARTIAL`
- **Última revisión documental:** 2026-10-25
- **Repositorio:** `ALBRA8/DESPACHO-JURIDICO`
- **Rama observada:** `main`
- **HEAD observado antes de crear esta carpeta:** `1bcf8290d06531cedb94d0638f4b0542991dcaea`
- **Estado de pruebas del HEAD:** `UNVERIFIED` en esta revisión documental

## 1. Propósito del proyecto

Construir un organismo digital especializado en el trabajo jurídico, con jurisdicción inicial en Colombia, separando la arquitectura del agente, las capacidades y el conocimiento jurídico verificable.

La separación crítica es:
- **ADN/runtime:** comportamiento, identidad, seguridad, razonamiento, herramientas, memoria, evidencia y trazabilidad.
- **Conocimiento jurídico:** normas, jurisprudencia, doctrina y metadatos que deben proceder de fuentes identificables y verificables.
- **Arnés/adaptadores:** mecanismos para conectar o sustituir el agente y registrar conocimiento/capacidades sin mezclarlo con la identidad del agente.

## 2. Estado técnico observado

El último commit consultado, `1bcf829` (HEAD completo indicado arriba), se titula `feat: MIGRACIÓN PROYECTO → ARNÉS — AGENTE-GENERAL montable`. Su descripción declara la creación de:
- `src/adapters/`: interfaz AgentAdapter y GeneralAdapter.
- `src/bridges/`: BridgeRegistry, ZaiSdkBridge y PythonBridge.
- `src/harness/`: SkillRegistry y KnowledgeRegistry.
- `src/bootstrap/`: inicialización y API del arnés.
- Siete módulos de conocimiento declarados: `legal-schemas`, `legal-sources`, `legal-temporal`, `corpus-pilot`, `firewall-policies`, `legal-sops` y `specialists`.

El mensaje del commit declara 30 pruebas del arnés y 242/242 pruebas totales aprobadas, además de lint correcto. **Estos resultados se conservan como declaraciones del commit; no se volvieron a ejecutar ni se verificó CI durante la creación de este contexto.**

## 3. Estado del conocimiento jurídico

La documentación existente registra una auditoría de corpus V1.0 con fallos graves por contenido sintético o mal identificado. El informe V1.1 posterior declara que se sustituyeron o eliminaron esos elementos y que se conservaron tres documentos normativos con doce artículos. Ver [Estado del corpus jurídico](./ESTADO_CORPUS_JURIDICO.md).

**No declarar el corpus completo ni la jurisprudencia disponible.** El propio informe V1.1 declara que no se incorporó jurisprudencia real, que no se conservó doctrina y que el corpus es pequeño. Su resultado PASS es el resultado reportado en ese documento; la revisión actual no reproduce independientemente las pruebas ni compara el contenido almacenado con las fuentes oficiales.

## 4. Documentación fuente ya existente

Los informes técnicos históricos siguen en `docs/` en la raíz del repositorio. Esta carpeta los indexa; no los reemplaza ni los mueve:
- `docs/ARCHITECTURE.md`
- `docs/AUDIT_FINAL_PRECORPUS.md`
- `docs/AUDIT_INDEPENDENT_V1.md`
- `docs/AUDIT_INDEPENDENT_V2.md`
- `docs/CORPUS_PILOT_AUDIT_V1.md`
- `docs/CORPUS_PILOT_AUDIT_V1_1.md`
- `docs/FINAL_REPORT.md`
- `docs/IMPROVEMENTS.md`
- `docs/PARITY_REPORT.md`
- `docs/V1.6_INTEGRATION_COMPLETE.md`

## 5. Bloqueos y cautelas de continuidad

1. No confundir el resultado declarado en un informe con verificación independiente actual.
2. No reintroducir documentos sintéticos para completar categorías vacías.
3. No afirmar que una URL accesible o bien formada autentica por sí sola la fuente o el contenido.
4. No asumir que las afirmaciones de los informes antiguos describen necesariamente el HEAD actual.
5. Antes de declarar una fase cerrada, inspeccionar el código vigente, reproducir las pruebas pertinentes y conservar evidencia con commit, comandos, resultados y limitaciones.
6. La transferencia del ADN al futuro agente contador es una intención futura, no una tarea técnica aprobada ni iniciada.

## 6. Próximo paso recomendado

Realizar una reconciliación del HEAD actual contra los informes existentes: revisar el arnés y los siete módulos declarados, comprobar CI/pruebas del commit, verificar los archivos reales del corpus y registrar por separado resultados reproducidos, limitaciones y trabajo pendiente.
