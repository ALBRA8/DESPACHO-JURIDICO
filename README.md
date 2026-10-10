# DESPACHO JURÍDICO DIGITAL ALBRA

> **Agente Base V1.0** — El organismo completo, sin conocimiento jurídico cargado todavía.

[![Tests](https://github.com/ALBRA8/DESPACHO-JURIDICO/actions/workflows/ci.yml/badge.svg)](./.github/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-Proprietary%20ALBRA-red)

---

## 1. Qué es ALBRA

ALBRA es un **organismo digital** diseñado para ser el núcleo inteligente de un despacho jurídico. Esta primera versión **NO** incluye:

- ❌ Conocimiento jurídico cargado (normas, jurisprudencia, doctrina)
- ❌ Subagentes especializados (constitucional, civil, penal, etc.)
- ❌ Integraciones activas con APIs externas

Pero **SÍ** incluye toda la **arquitectura** para que esa carga se haga progresivamente:

- ✅ 30 órganos del ADN ALBRA operativos
- ✅ Memoria vectorial con 6 categorías separadas
- ✅ MCP/MSP server + client
- ✅ Doctor (sistema de diagnóstico)
- ✅ Trazabilidad de evidencia y provenance
- ✅ HITL para acciones sensibles
- ✅ Adapters de canales (WhatsApp, Telegram, texto, voz)
- ✅ Workflow engine con estados
- ✅ Handoff protocol para futuros subagentes
- ✅ Providers desacoplados (Mock, OpenAI, Anthropic)
- ✅ Suite de tests

## 2. Principios rectores

1. **GitHub es la ÚNICA FUENTE DE VERDAD del código.**
2. El **Constructor** es el único autorizado a modificar código.
3. El conocimiento jurídico **NO** es código. Se carga después.
4. **NO se inventan** APIs, credenciales, ni integraciones.
5. Toda acción sensible requiere **aprobación humana** (HITL).
6. Trazabilidad obligatoria: `SOURCE → EVIDENCE → CONCLUSION → ACTION`.
7. Separación estricta: `DATOS, FUENTES, EVIDENCIA, INFERENCIAS, CONCLUSIONES, ACCIONES`.

## 3. Arquitectura

```
albra/
├── identity/          # Identidad + agente orquestador
├── runtime/           # Loop runtime + contexto
├── reasoning/         # Motor de razonamiento con capas
├── tools/             # Framework de herramientas
├── capabilities/      # Capability system
├── mcp/               # MCP Server + Client
├── memory/            # memorydv (vectorial, 6 categorías)
├── doctor/            # Diagnóstico de salud
├── multimodal/        # Texto, voz, audio, imagen, documento
├── files/             # I/O con trazabilidad
├── comms/             # Router + adapters (WA/TG/text/voice)
├── research/          # Investigación con fuentes oficiales
├── evidence/          # Cadena de evidencia + provenance
├── security/          # Auth, authz, HITL
├── events/            # Event bus
├── workflows/         # Workflow engine
├── handoffs/          # Handoff protocol (futuros subagentes)
├── providers/         # LLM providers desacoplados
├── resilience/        # Retry, fallback, recovery
├── observability/     # Logger, metrics, tracer
├── audit/             # Audit log inmutable
├── knowledge/         # Capa de conocimiento (vacía - se carga después)
│   └── colombia/      # Fuentes oficiales CO declaradas, contenido vacío
├── api/               # FastAPI HTTP (opcional)
└── cli.py             # CLI con click
```

## 4. Instalación

```bash
git clone https://github.com/ALBRA8/DESPACHO-JURIDICO.git
cd DESPACHO-JURIDICO
pip install -e .

# Opcional - server HTTP
pip install -e ".[server]"

# Opcional - vector DB
pip install -e ".[vector]"

# Opcional - dev
pip install -e ".[dev]"
```

## 5. Uso

### CLI

```bash
# Info del agente
albra info

# Diagnóstico completo
albra doctor

# Órganos activos
albra organs

# Capacidades
albra capabilities

# Herramientas
albra tools

# Memoria stats
albra memory

# Modo chat por terminal
albra chat

# Servidor HTTP
albra serve
```

### API HTTP (opcional)

```bash
albra serve
# → http://localhost:8000
# → /docs (Swagger)
```

Endpoints:
- `GET /` — Identidad
- `GET /health` — Diagnóstico
- `POST /chat` — Chat
- `GET /tools` — Tools
- `GET /capabilities` — Capacidades
- `GET /organs` — Órganos
- `GET /memory/stats` — Memoria
- `GET /audit` — Audit log
- `GET /evidence` — Evidencia

### Programáticamente

```python
import asyncio
from albra.identity.agent import get_agent

async def main():
    agent = get_agent()
    await agent.boot()
    result = await agent.process("hola", user="test", channel="text")
    print(result["reply"])
    await agent.shutdown()

asyncio.run(main())
```

## 6. Configuración

Copia `.env.example` a `.env` y completa los valores reales.

| Variable | Default | Descripción |
|----------|---------|-------------|
| `ALBRA_ENVIRONMENT` | `development` | `development` o `production` |
| `ALBRA_MEMORY_BACKEND` | `inmemory` | `inmemory` o `sqlite` |
| `ALBRA_MEMORY_PATH` | `./data/memory.db` | Path a DB de memoria |
| `ALBRA_DEFAULT_PROVIDER` | `mock` | `mock`, `openai`, `anthropic` |
| `ALBRA_OPENAI_API_KEY` | `` | API key OpenAI |
| `ALBRA_WHATSAPP_ENABLED` | `false` | Activar adapter WhatsApp |
| `ALBRA_TELEGRAM_ENABLED` | `false` | Activar adapter Telegram |
| `ALBRA_JWT_SECRET` | `change-me` | Secreto JWT |
| `ALBRA_KNOWLEDGE_JURISDICTION` | `CO` | Colombia |

## 7. Tests

```bash
pytest
```

## 8. Criterios de "Nacido" (verificados)

1. ✅ Identidad propia
2. ✅ Runtime funcional
3. ✅ Razonamiento con capas separadas
4. ✅ Tools
5. ✅ MCP/MSP
6. ✅ Doctor
7. ✅ memorydv
8. ✅ Texto
9. ✅ Preparado para voz/audio
10. ✅ Preparado para imágenes
11. ✅ Lectura de documentos
12. ✅ Generación de archivos
13. ✅ Arquitectura de comunicación
14. ✅ Preparado para WhatsApp
15. ✅ Preparado para Telegram
16. ✅ Investigación
17. ✅ Evidencia
18. ✅ Provenance
19. ✅ Trazabilidad
20. ✅ Seguridad
21. ✅ Permisos
22. ✅ Human-in-the-loop
23. ✅ Observabilidad
24. ✅ Auditoría
25. ✅ Resiliencia
26. ✅ Recuperación
27. ✅ Providers desacoplados
28. ✅ Workflows
29. ✅ Handoffs
30. ✅ Capability system
31. ✅ Testing
32. ✅ Preparado para conocimiento jurídico
33. ✅ No requiere subagentes especializados
34. ✅ No confunde conocimiento con código
35. ✅ No modifica la fuente de verdad fuera del Constructor
36. ✅ Puede evolucionar sin reconstruirse

## 9. Próximas fases

- **Fase 2**: Carga de conocimiento jurídico Colombia (Constitución, Códigos, Jurisprudencia)
- **Fase 3**: Subagentes especializados (civil, penal, laboral, etc.)
- **Fase 4**: Integración real con WhatsApp Business / Telegram Bot
- **Fase 5**: Multimodalidad real (VLM, ASR/TTS)
- **Fase 6**: Despliegue productivo

## 10. Licencia

Propietaria - ALBRA. Ver LICENSE.
