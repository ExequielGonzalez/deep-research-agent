# deep-research-agent — Documentación Técnica

## Visión General

`deep-research-agent` es un agente autónomo de investigación profunda (Deep Research) basado en **LangGraph** que planifica, ejecuta búsquedas, extrae evidencia, reflexiona sobre el conocimiento adquirido y sintetiza informes analíticos. Está diseñado para tareas de investigación complejas y prolongadas con intervención humana asíncrona (Human-in-the-Loop).

## Stack Tecnológico

| Capa | Tecnología | Propósito |
|------|-----------|-----------|
| Orquestación | LangGraph 1.2.1 | StateGraph cíclico con checkpoints y HITL |
| Backend Web | FastAPI + Uvicorn | API REST + SSE para frontend |
| Frontend | Vue 3 + Vite (PWA) | Interfaz de usuario opcional |
| Persistencia | SQLite (dev) / Postgres (prod) | Checkpointers + RunStore |
| LLM | OpenAI / Ollama | Planificación, reflexión, síntesis |
| Búsqueda | DuckDuckGo / Tavily / Serper | Recuperación de fuentes web |
| Extracción | HTMLParser nativo | Extracción de texto de URLs |
| Validación | Pydantic v2 | Schemas JSON estrictos para output LLM |

## Arquitectura del Sistema

### Capas

```
┌──────────────────────────────────────────────┐
│                Web Layer (FastAPI)             │
│  /api/runs, /api/runs/{id}/events (SSE)       │
├──────────────────────────────────────────────┤
│            Runtime Layer (LangGraph)           │
│  ResearchRuntimeService → StateGraph.astream  │
│  Checkpointer → SQLite/Postgres               │
├──────────────────────────────────────────────┤
│            Service Layer (asyncio)             │
│  LLMService │ SearchService │ ContentExtractor│
│  ReportFormatter                               │
├──────────────────────────────────────────────┤
│            Domain Layer (Pydantic)             │
│  Models: PlanTask, SourceRecord, EvidenceRecord│
│  State: ResearchGraphState (TypedDict)         │
└──────────────────────────────────────────────┘
```

### Flujo del Grafo

El grafo principal se define en [`runtime/graph.py`](src/deep_research_agent/runtime/graph.py:462) con esta topología:

```
START → plan_research → prepare_plan_review → await_plan_review
                                                     │
                                          ┌──────────┼──────────┐
                                          │ STOP     │ CLARIFY  │ APPROVE
                                          ▼          ▼          ▼
                                      cancel_run  apply_plan_feedback → plan_research
                                                              begin_iteration
                                                                  │
                                                              search_sources
                                                                  │
                                                              extract_evidence
                                                                  │
                                                              reflect_research
                                                                  │
                                                    ┌─────────────┴─────────────┐
                                                    │ needs_more && iter < max  │ else
                                                    ▼                           ▼
                                              begin_iteration      prepare_sufficiency_review
                                                                           │
                                                                       await_sufficiency_review
                                                                           │
                                                              ┌────────────┼──────────┐
                                                              │ STOP       │ APPROVE │ CONTINUE
                                                              ▼            ▼         ▼
                                                          cancel_run  synthesize  apply_sufficiency_feedback
                                                                          │              │
                                                                          ▼              ▼
                                                                        END        begin_iteration
```

### Puntos de Interrupción Humana (HITL)

1. **Plan Approval** — Después de `plan_research`. El humano revisa las tareas planificadas y puede: `APPROVE`, `CLARIFY` (con feedback), o `STOP`.
2. **Sufficiency Review** — Después de `reflect_research` cuando el agente considera suficiente o se alcanza el límite de iteraciones. El humano puede: `APPROVE` (sintetizar), `CONTINUE` (seguir investigando), o `STOP`.

## Servicios

### LLM ([`services/llm.py`](src/deep_research_agent/services/llm.py:434))

- `OpenAIResearchLLMService`: Usa `response_format` con `json_schema` para output estructurado.
- `OllamaResearchLLMService`: Usa `format` con `model_json_schema()`.
- Ambos heredan de `JSONSchemaLLMService` que define los métodos:
  - `plan_research()` → `ResearchPlan`
  - `reflect_research()` → `ReflectionOutput`
  - `synthesize_report()` → `SynthesizedReport`

### Búsqueda ([`services/search.py`](src/deep_research_agent/services/search.py:21))

- `DuckDuckGoSearchService`: Scrapea `html.duckduckgo.com/html/`. No requiere API key.
- `TavilySearchService`: API REST. Requiere `DEEP_RESEARCH_TAVILY_API_KEY`.
- `SerperSearchService`: API REST. Requiere `DEEP_RESEARCH_SERPER_API_KEY`.

### Extracción ([`services/extraction.py`](src/deep_research_agent/services/extraction.py:35))

- `ContentExtractor`: Descarga HTML de cada URL, extrae texto plano con HTMLParser nativo, selecciona los pasajes más relevantes por solapamiento de keywords.

### Reportes ([`services/reporting.py`](src/deep_research_agent/services/reporting.py:19))

- `ReportFormatter`: Convierte `SynthesizedReport` en markdown con citas numeradas.

## Estados del Grafo (Reducers)

Definidos en [`domain/state.py`](src/deep_research_agent/domain/state.py:106). Cada clave tiene un reducer con semántica de merge/append:

| Clave | Reducer | Comportamiento |
|-------|---------|----------------|
| `notes` | `merge_notes` | Append, dedup exacto, preserva orden |
| `plan_tasks` | `merge_plan_tasks` | Merge por `task_id` |
| `sources` | `merge_sources` | Dedup por `canonical_url`, mergea `task_ids` |
| `evidence` | `merge_evidence` | Merge por `evidence_id` |
| `reflections` | `merge_reflections` | Merge por `reflection_id` |
| `human_decisions` | `merge_human_decisions` | Merge por `decision_id` |
| `report_sections` | `merge_report_sections` | Merge por `section_id` |
| `citation_records` | `merge_citations` | Merge por `source_id` |

## API REST

Endpoints expuestos por [`web/app.py`](src/deep_research_agent/web/app.py):

| Endpoint | Método | Propósito |
|----------|--------|-----------|
| `/api/health` | GET | Health check |
| `/api/config` | GET | Configuración por defecto |
| `/api/runs` | GET | Listar runs |
| `/api/runs/pending` | GET | Runs esperando input humano |
| `/api/runs` | POST | Crear y ejecutar un nuevo run |
| `/api/runs/{thread_id}` | GET | Estado del run |
| `/api/runs/{thread_id}/decision` | POST | Enviar decisión humana |
| `/api/runs/{thread_id}/events` | GET | SSE en tiempo real |
| `/api/runs/{thread_id}/report` | GET | Descargar reporte markdown |
| `/api/settings` | GET/POST | Configuración persistente |
| `/api/models` | GET | Catálogo de modelos del proveedor |

### Eventos SSE

El runtime emite eventos via un emisor `ContextVar` ([`events.py`](src/deep_research_agent/runtime/events.py:26)):

- `snapshot` — Estado completo después de cada nodo del grafo
- `llm_stage_started` — Inicio de llamada LLM (con nombre de fase)
- `llm_reasoning` — Razonamiento intermedio (OpenAI only)
- `llm_output_preview` — Vista previa del output LLM
- `run_task_started/finished/cancelled/failed` — Ciclo de vida de la tarea background

## Fiabilidad y Timeouts

Lección crítica aprendida en producción: las llamadas de red con `urllib` dentro de `asyncio.to_thread()` **no propagan el timeout del socket TCP al nivel de la corrutina asyncio**.

### Estrategia de Tres Capas

| Capa | Ubicación | Mecanismo | Default |
|------|-----------|-----------|---------|
| Timeout global del grafo | [`_execute_graph`](src/deep_research_agent/runtime/service.py:176) | `asyncio.timeout(max(60, llm_timeout * 3))` | 1800s |
| Timeout LLM | [`_http_json_request`](src/deep_research_agent/services/llm.py:584) | `asyncio.wait_for(task, timeout=timeout_seconds)` | 600s (configurable) |
| Timeout búsqueda/extracción | [`_post_json`](src/deep_research_agent/services/search.py:162) / [`_fetch_text`](src/deep_research_agent/services/extraction.py:81) | `asyncio.wait_for(..., timeout=35)` | 35s |

**Regla**: Todo `asyncio.to_thread()` con bloqueo de red **debe** tener `asyncio.wait_for()`. Es el patrón de fiabilidad más importante del código.

## CLI

```bash
deep-research-agent run --query "..." [--max-iterations N]
deep-research-agent resume --thread-id <id> --decision approve|clarify|continue|stop [--summary "..."]
deep-research-agent list-pending [--limit N]
```

## Variables de Entorno

Todas con prefijo `DEEP_RESEARCH_`. Ver [`settings.py`](src/deep_research_agent/settings.py:17).

| Variable | Default | Descripción |
|----------|---------|-------------|
| `MODEL_PROVIDER` | `openai` | `openai` o `ollama` |
| `MODEL_NAME` | `gpt-4.1-mini` | Modelo LLM |
| `OPENAI_API_KEY` | — | API key OpenAI |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Base URL (útil para providers compatibles) |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Base URL Ollama |
| `DEFAULT_SEARCH_PROVIDER` | `none` | `none`, `tavily`, `serper` |
| `TAVILY_API_KEY` | — | API key Tavily |
| `SERPER_API_KEY` | — | API key Serper |
| `MAX_ITERATIONS` | `6` | Iteraciones máximas del bucle investigación |
| `MAX_SOURCES_PER_TASK` | `8` | Fuentes máximas por tarea |
| `LLM_REQUEST_TIMEOUT_SECONDS` | `600` | Timeout para llamadas LLM |
| `PERSISTENCE_BACKEND` | `sqlite` | `sqlite` o `postgres` |

## Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

Los tests usan servicios falsos ([`tests/support.py`](tests/support.py)) — no requieren API keys. El test de integración `test_runtime_flow.py` ejercita el ciclo completo del grafo con servicios simulados.

## Docker

```bash
# Iniciar Postgres + app
./scripts/compose-agent.sh bootstrap
./scripts/compose-agent.sh run --query "¿...?"
./scripts/compose-agent.sh down
```

El Dockerfile construye el frontend Vue en stage 1 y el backend Python en stage 2.
