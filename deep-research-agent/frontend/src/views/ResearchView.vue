<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue'
import { useResearchStore } from '@/stores/useResearchStore'
import { useSettingsStore } from '@/stores/useSettingsStore'
import QueryForm from '@/components/research/QueryForm.vue'
import TimelinePanel from '@/components/research/TimelinePanel.vue'
import LiveFeedPanel from '@/components/research/LiveFeedPanel.vue'
import ReportPanel from '@/components/research/ReportPanel.vue'
import TasksPanel from '@/components/research/TasksPanel.vue'
import SourcesPanel from '@/components/research/SourcesPanel.vue'
import ApprovalBox from '@/components/research/ApprovalBox.vue'
import StatusPill from '@/components/common/StatusPill.vue'
import ProgressBar from '@/components/common/ProgressBar.vue'
import type { CreateRunRequest, HumanDecisionType } from '@/types'

const researchStore = useResearchStore()
const settingsStore = useSettingsStore()

// ── Computed ────────────────────────────────────────────────────────

const activeRun = computed(() => researchStore.activeRun)
const status = computed(() => researchStore.activeRunStatus)
const isRunning = computed(() => researchStore.isRunning)
const isComplete = computed(() => researchStore.isComplete)
const isInterrupted = computed(() => researchStore.isInterrupted)
const hasReport = computed(() => researchStore.hasFinalReport)
const pendingInput = computed(() => researchStore.pendingHumanInput)
const events = computed(() => researchStore.activeEvents)
const isConnecting = computed(() => researchStore.isConnecting)
const isConnected = computed(() => researchStore.isConnected)
const runError = computed(() => researchStore.runError)

const models = computed(() => settingsStore.models)

// When research completes -> we hide progress panels and show only the report
const showProgressOnly = computed(() => {
  return isRunning.value || isInterrupted.value
})

const showReportOnly = computed(() => {
  return isComplete.value && hasReport.value
})

const showEmptyState = computed(() => {
  return !activeRun.value && !isConnecting.value && !isConnected.value
})

// ── Lifecycle ───────────────────────────────────────────────────────

onMounted(async () => {
  if (researchStore.runsList.length === 0) {
    await researchStore.fetchRuns()
  }
  if (researchStore.runsList.length > 0 && !activeRun.value) {
    researchStore.selectRun(researchStore.runsList[0].thread_id)
    researchStore.connectToSse(researchStore.runsList[0].thread_id)
  }
})

onUnmounted(() => {
  researchStore.disconnectSse()
})

// ── Handlers ────────────────────────────────────────────────────────

async function handleSubmit(payload: CreateRunRequest) {
  await researchStore.createRun(payload)
}

async function handleDecision(decision: HumanDecisionType, summary: string) {
  if (!activeRun.value) return
  await researchStore.submitDecision(
    activeRun.value.thread_id,
    decision,
    summary,
  )
  researchStore.connectToSse(activeRun.value.thread_id)
}

function threadId() {
  return activeRun.value?.thread_id ?? ''
}
</script>

<template>
  <div class="research-view">
    <!-- Empty State -->
    <div v-if="showEmptyState" class="empty-view animate-fade-in">
      <div class="empty-view-content">
        <h2 class="empty-title">Launch a Research Investigation</h2>
        <p class="empty-desc">
          Enter your research query and the agent will plan, search, extract,
          reflect, and synthesize a comprehensive report.
        </p>
        <QueryForm
          :is-creating="researchStore.isCreatingRun"
          :models="models"
          :error="runError"
          @submit="handleSubmit"
        />
        <!-- Past runs -->
        <div v-if="researchStore.runsList.length > 0" class="past-runs">
          <h3 class="past-runs-title">Recent Runs</h3>
          <div class="runs-grid">
            <button
              v-for="run in researchStore.runsList.slice(0, 5)"
              :key="run.thread_id"
              class="run-card"
              @click="
                researchStore.selectRun(run.thread_id);
                researchStore.connectToSse(run.thread_id);
              "
            >
              <div class="run-card-header">
                <span class="run-card-query">{{ run.query }}</span>
                <StatusPill :status="run.status" />
              </div>
              <p class="run-card-meta text-mono">
                {{ new Date(run.created_at).toLocaleDateString() }}
                {{ run.runtime_config?.model_name ? `· ${run.runtime_config.model_name}` : '' }}
              </p>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Active Research View -->
    <div v-else class="active-research">
      <!-- Status Bar -->
      <div class="status-bar">
        <div class="status-bar-left">
          <h2 class="query-title">{{ activeRun?.query ?? 'Research' }}</h2>
          <StatusPill
            v-if="status"
            :status="status"
          />
        </div>
        <div class="status-bar-right">
          <span v-if="isConnecting" class="connecting-badge">Connecting...</span>
          <span v-else-if="isConnected" class="connected-badge">Live</span>
          <span class="thread-id text-mono" :title="threadId()">
            {{ threadId().slice(0, 12) }}...
          </span>
          <button
            class="new-btn"
            @click="researchStore.disconnectSse(); researchStore.latestRun = null;"
            title="Start new research"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18">
              <path d="M12 5v14m0 0l-5-5m5 5l5-5" />
            </svg>
            New
          </button>
        </div>
      </div>

      <!-- HITL Approval -->
      <ApprovalBox
        v-if="isInterrupted && pendingInput"
        :input="pendingInput"
        @decision="handleDecision"
      />

      <!-- Progress View (during research) -->
      <div v-if="showProgressOnly" class="progress-view animate-fade-in">
        <!-- Progress Bar -->
        <ProgressBar
          :current="((activeRun?.state as Record<string, unknown>)?.iteration_count as number) ?? 0"
          :max="6"
          label="Iteration"
        />

        <div class="progress-grid">
          <div class="progress-sidebar">
            <TimelinePanel
              v-if="activeRun"
              :run="(activeRun as any)"
            />
            <LiveFeedPanel :events="events" />
          </div>
          <div class="progress-main">
            <ReportPanel
              v-if="activeRun"
              :run="(activeRun as any)"
            />
            <div class="support-grid">
              <TasksPanel
                :tasks="((activeRun?.state as Record<string, unknown>)?.plan_tasks as any[]) ?? []"
              />
              <SourcesPanel
                :sources="((activeRun?.state as Record<string, unknown>)?.sources as any[]) ?? []"
              />
            </div>
          </div>
        </div>
      </div>

      <!-- Report Only View (after completion) -->
      <div v-else-if="showReportOnly && activeRun" class="report-view animate-fade-in">
        <div class="report-container">
          <ReportPanel :run="(activeRun as any)" />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.research-view {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  animation: fadeIn var(--transition-slow) forwards;
}

/* ── Empty State ─────────────────────────────────────────────────── */

.empty-view {
  display: flex;
  justify-content: center;
  padding: var(--space-8) 0;
}

.empty-view-content {
  max-width: 680px;
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
}

.empty-title {
  font-size: 1.8rem;
  font-weight: 700;
  text-align: center;
}

.empty-desc {
  text-align: center;
  color: var(--muted);
  font-size: 1rem;
  line-height: 1.6;
  max-width: 540px;
  margin: 0 auto;
}

.past-runs {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  margin-top: var(--space-4);
}

.past-runs-title {
  font-family: var(--font-body);
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.runs-grid {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.run-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: var(--space-3) var(--space-4);
  background: var(--surface-strong);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  cursor: pointer;
  text-align: left;
  width: 100%;
  transition: all var(--transition-fast);
}

.run-card:hover {
  border-color: var(--accent-medium);
  box-shadow: var(--shadow-sm);
}

.run-card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--space-3);
}

.run-card-query {
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--ink);
  line-height: 1.35;
}

.run-card-meta {
  font-size: 0.75rem;
}

/* ── Status Bar ──────────────────────────────────────────────────── */

.status-bar {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--space-4);
  flex-wrap: wrap;
}

.status-bar-left {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
}

.query-title {
  font-size: 1.2rem;
  font-weight: 600;
  line-height: 1.25;
}

.status-bar-right {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
}

.connecting-badge,
.connected-badge {
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 3px 10px;
  border-radius: var(--radius-full);
}

.connecting-badge {
  background: var(--warm-soft);
  color: var(--warm);
  animation: pulse 1.5s ease-in-out infinite;
}

.connected-badge {
  background: var(--success-soft);
  color: var(--success);
}

.thread-id {
  font-size: 0.72rem;
}

.new-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--line-strong);
  border-radius: var(--radius);
  background: var(--surface-strong);
  font-family: var(--font-body);
  font-size: 0.8rem;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.new-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}

/* ── Progress View ───────────────────────────────────────────────── */

.progress-view {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.progress-grid {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: var(--space-4);
  align-items: start;
}

.progress-sidebar {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.progress-main {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  min-width: 0;
}

.support-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-4);
}

/* ── Report View (after completion) ──────────────────────────────────── */

.report-view {
  display: flex;
  justify-content: center;
}

.report-container {
  max-width: 860px;
  width: 100%;
}

/* ── Responsive ──────────────────────────────────────────────────── */

@media (max-width: 1024px) {
  .progress-grid {
    grid-template-columns: 1fr;
  }
  .support-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 600px) {
  .status-bar {
    flex-direction: column;
  }
}
</style>
