// ═══════════════════════════════════════════════════════════════════════════
// Deep Research Agent — TypeScript Types
// ═══════════════════════════════════════════════════════════════════════════

// ─── API Config ──────────────────────────────────────────────────────────

export interface AppConfig {
  default_model_name: string
  default_openai_base_url: string
  default_llm_request_timeout_seconds: number
  default_report_output_dir: string
  suggested_local_base_url: string
}

export interface AgentSettings {
  openai_api_key: string
  openai_base_url: string
  ollama_base_url: string
  default_search_provider: string
  searxng_pool_size: number
  searxng_selected_instances: string[]
  searxng_selected_at: string | null
  tavily_api_key: string
  serper_api_key: string
  has_tavily_api_key: boolean
  has_serper_api_key: boolean
  max_iterations: number
  max_sources_per_task: number
  total_token_budget: number
  max_notes: number
}

export interface ModelInfo {
  id: string
  object?: string
  created?: number
  owned_by?: string
  base_url: string
}

export interface RuntimeConfig {
  model_provider?: string
  model_name?: string
  openai_base_url?: string
  llm_request_timeout_seconds?: number
  default_search_provider?: string
  [key: string]: unknown
}

// ─── Run / State Types ───────────────────────────────────────────────────

export type RunStatus =
  | 'created'
  | 'running'
  | 'interrupted'
  | 'completed'
  | 'failed'
  | 'cancelled'

export type HumanDecisionType = 'approve' | 'clarify' | 'continue' | 'stop'

export interface HumanReviewRequest {
  review_id: string
  review_kind: string
  prompt: string
  allowed_decisions: HumanDecisionType[]
  context?: Record<string, unknown>
  plan_title?: string | null
  plan_summary?: string | null
  coverage_matrix?: Record<string, unknown> | null
  open_gaps?: string[]
  discarded_sources?: Record<string, unknown>[]
  conflicts?: Record<string, unknown>[]
  confidence_score?: number
  structured_options?: Record<string, unknown>[]
}

export interface PlanTask {
  task_id: string
  title: string
  description: string
  search_query: string
  status: 'todo' | 'in_progress' | 'done' | 'blocked' | 'failed'
  priority: number
  depends_on: string[]
  section_title?: string
  success_criteria?: string[]
  expected_sections?: string[]
  preferred_source_types?: string[]
  sufficiency_criteria?: Record<string, unknown>
}

export interface SourceRecord {
  source_id: string
  title: string
  url: string
  canonical_url?: string
  provider: string
  source_type: string
  snippet?: string
  task_ids: string[]
  retrieved_at?: string
  published_at?: string
  relevance_score?: number
  reliability_score?: number
  authority_tier?: 'PRIMARY' | 'CONTEXTUAL' | 'EXCLUDED'
  selection_justification?: string
  discovery_iteration?: number
}

export interface ReportSection {
  section_id: string
  title: string
  status: 'planned' | 'draft' | 'complete'
  content_markdown: string
  citations: string[]
  source_ids: string[]
  summary_points: string[]
}

export interface ResearchRun {
  thread_id: string
  query: string
  status: RunStatus
  created_at: string
  updated_at: string
  last_message?: string
  is_running: boolean
  runtime_config?: RuntimeConfig
  state?: Record<string, unknown>
  pending_human_input?: HumanReviewRequest | null
  report?: string
  interrupts?: unknown[]
}

export interface RunListItem {
  thread_id: string
  query: string
  status: RunStatus
  created_at: string
  updated_at: string
  last_message?: string
  is_running: boolean
  runtime_config?: RuntimeConfig
  state?: Record<string, unknown>
  pending_human_input?: HumanReviewRequest | null
}

export interface CreateRunRequest {
  query: string
  audience?: string
  objective?: string
  constraints?: string[]
  deliverable_format?: string
  max_iterations?: number
  model_name?: string
  openai_base_url?: string
  openai_api_key?: string
  llm_request_timeout_seconds?: number
}

export interface SubmitDecisionRequest {
  decision: HumanDecisionType
  summary?: string
  payload?: Record<string, unknown>
}

export interface SaveSettingsRequest {
  openai_api_key?: string
  openai_base_url?: string
  ollama_base_url?: string
  default_search_provider?: string
  tavily_api_key?: string
  serper_api_key?: string
  clear_tavily_api_key?: boolean
  clear_serper_api_key?: boolean
  max_iterations?: number
  max_sources_per_task?: number
  total_token_budget?: number
  max_notes?: number
}

export interface RefreshSearxngPoolResponse {
  instances: string[]
  selected_at: string
}

// ─── SSE Event Types ─────────────────────────────────────────────────────

export type SseEventType =
  | 'snapshot'
  | 'llm_stage_started'
  | 'llm_reasoning'
  | 'llm_output_preview'
  | 'run_task_failed'
  | 'run_task_started'
  | 'run_task_finished'
  | 'stream_end'

export interface SseSnapshotEvent {
  type: 'snapshot'
  thread_id: string
  data: {
    thread_id: string
    query: string
    status: RunStatus
    message: string
    pending_human_input?: HumanReviewRequest | null
    interrupts: unknown[]
    state: Record<string, unknown>
    runtime_config?: Record<string, unknown>
    resume_supported: boolean
    [key: string]: unknown
  }
}

export interface SseLlmStageStartedEvent {
  type: 'llm_stage_started'
  thread_id: string
  data: {
    stage: string
    node?: string
    details?: Record<string, unknown>
  }
}

export interface SseLlmReasoningEvent {
  type: 'llm_reasoning'
  thread_id: string
  data: {
    content: string
  }
}

export interface SseLlmOutputPreviewEvent {
  type: 'llm_output_preview'
  thread_id: string
  data: {
    content: string
  }
}

export interface SseRunTaskFailedEvent {
  type: 'run_task_failed'
  thread_id: string
  data: {
    task_name: string
    error: string
    node?: string
  }
}

export interface SseStreamEndEvent {
  type: 'stream_end'
  thread_id: string
  data: {
    status?: string
  }
}

export type SseEvent =
  | SseSnapshotEvent
  | SseLlmStageStartedEvent
  | SseLlmReasoningEvent
  | SseLlmOutputPreviewEvent
  | SseRunTaskFailedEvent
  | SseStreamEndEvent

export interface EventLogEntry {
  id: string
  type: string
  thread_id: string
  timestamp: string
  data: Record<string, unknown>
}

// ─── Graph State Helpers (extracted from run state) ──────────────────────

export interface ResearchGraphState {
  query?: string
  plan_tasks?: PlanTask[]
  sources?: SourceRecord[]
  notes?: string[]
  report_sections?: ReportSection[]
  last_error?: string
  final_report_title?: string
  final_report_markdown?: string
  final_report_path?: string
  final_report_status?: string
  iteration_count?: number
  coverage_metrics?: {
    total_evidence?: number
    total_tasks?: number
    covered_tasks?: number
    coverage_pct?: number
    task_coverage?: Record<string, {
      evidence_count: number
      source_count: number
      avg_confidence: number
      has_contradictions: boolean
      primary_sources: string[]
    }>
  }
  [key: string]: unknown
}

export function extractGraphState(run: ResearchRun | RunListItem): ResearchGraphState {
  return (run.state ?? {}) as ResearchGraphState
}
