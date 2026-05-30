<script setup lang="ts">
import { computed, ref } from 'vue'
import type { ResearchRun, ResearchGraphState, ReportSection } from '@/types'
import MarkdownRenderer from '@/components/common/MarkdownRenderer.vue'
import { api } from '@/services/api'

const props = defineProps<{
  run: ResearchRun
}>()

const isExporting = ref(false)
const exportError = ref<string | null>(null)

const graph = computed<ResearchGraphState>(() => {
  return (props.run.state ?? {}) as ResearchGraphState
})

const hasReport = computed(() => {
  return typeof graph.value.final_report_markdown === 'string' &&
    graph.value.final_report_markdown.trim().length > 0
})

const sections = computed<ReportSection[]>(() => {
  return graph.value.report_sections ?? []
})

async function exportMarkdown() {
  isExporting.value = true
  exportError.value = null
  try {
    const md = await api.getReportMarkdown(props.run.thread_id)
    const blob = new Blob([md], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${props.run.thread_id.slice(0, 8)}-report.md`
    a.click()
    URL.revokeObjectURL(url)
  } catch {
    exportError.value = 'Failed to export report'
  } finally {
    isExporting.value = false
  }
}
</script>

<template>
  <div class="report-panel">
    <div class="report-header">
      <div>
        <span class="text-eyebrow">Final Report</span>
      </div>
      <div class="report-actions">
        <span class="report-status">
          {{ graph.final_report_status || 'pending' }}
        </span>
        <button
          v-if="hasReport"
          class="btn btn-secondary"
          :disabled="isExporting"
          @click="exportMarkdown"
        >
          <svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="M12 5v14m0 0l-5-5m5 5l5-5" />
          </svg>
          {{ isExporting ? 'Exporting...' : 'Export Markdown' }}
        </button>
      </div>
    </div>

    <p v-if="graph.final_report_path" class="report-path text-mono">
      Saved to {{ graph.final_report_path }}
    </p>
    <p v-else-if="hasReport" class="report-path text-mono">
      Report ready for export.
    </p>

    <div v-if="exportError" class="export-error" role="alert">
      {{ exportError }}
    </div>

    <!-- Stats Grid -->
    <div class="stats-grid" v-if="graph.plan_tasks?.length || graph.sources?.length">
      <div class="stat-card">
        <strong>{{ graph.plan_tasks?.length ?? 0 }}</strong>
        <span>Tasks</span>
      </div>
      <div class="stat-card">
        <strong>{{ graph.sources?.length ?? 0 }}</strong>
        <span>Sources</span>
      </div>
      <div class="stat-card">
        <strong>{{ (graph.reflections as unknown[])?.length ?? 0 }}</strong>
        <span>Reflections</span>
      </div>
      <div class="stat-card">
        <strong>{{ graph.iteration_count ?? 0 }}</strong>
        <span>Iterations</span>
      </div>
    </div>

    <!-- Full Report Markdown -->
    <div v-if="hasReport" class="report-body-wrapper animate-fade-in">
      <MarkdownRenderer :content="graph.final_report_markdown ?? ''" />
    </div>

    <!-- Sections Preview -->
    <div v-if="sections.length > 0 && !hasReport" class="sections-list">
      <article
        v-for="section in sections"
        :key="section.section_id"
        class="section-card animate-fade-in"
      >
        <div class="section-header-row">
          <h4 class="section-title">{{ section.title }}</h4>
          <span
            class="section-status"
            :class="`section-status--${section.status}`"
          >
            {{ section.status }}
          </span>
        </div>
        <p class="section-content" v-if="section.content_markdown">
          {{ section.content_markdown }}
        </p>
      </article>
    </div>

    <div v-else-if="!hasReport" class="empty-report animate-fade-in">
      <p>Final report will appear after the workflow completes synthesis.</p>
    </div>
  </div>
</template>

<style scoped>
.report-panel {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.report-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--space-4);
}

.report-actions {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
}

.report-status {
  font-size: 0.78rem;
  font-weight: 600;
  padding: 4px 12px;
  border-radius: var(--radius-full);
  background: var(--accent-soft);
  color: var(--accent);
  text-transform: capitalize;
}

.report-path {
  font-size: 0.78rem;
  color: var(--muted);
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-4);
  border: 1px solid var(--line-strong);
  border-radius: var(--radius);
  background: var(--surface-strong);
  font-family: var(--font-body);
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.btn:hover:not(:disabled) {
  border-color: var(--accent);
  color: var(--accent);
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-icon {
  width: 16px;
  height: 16px;
}

.export-error {
  padding: var(--space-2) var(--space-3);
  background: var(--danger-soft);
  border: 1px solid var(--danger-medium);
  border-radius: var(--radius-sm);
  color: var(--danger);
  font-size: 0.82rem;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-2);
}

.stat-card {
  padding: var(--space-3);
  background: var(--surface-strong);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  text-align: center;
}

.stat-card strong {
  display: block;
  font-family: var(--font-mono);
  font-size: 1.4rem;
  font-weight: 700;
  color: var(--accent);
}

.stat-card span {
  font-size: 0.78rem;
  color: var(--muted);
  font-weight: 600;
}

.report-body-wrapper {
  background: var(--surface-strong);
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  padding: var(--space-6);
  max-height: 80vh;
  overflow-y: auto;
}

.sections-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.section-card {
  padding: var(--space-3) var(--space-4);
  background: var(--surface-strong);
  border: 1px solid var(--line);
  border-radius: var(--radius);
}

.section-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-3);
}

.section-title {
  font-family: var(--font-body);
  font-size: 0.9rem;
  font-weight: 600;
}

.section-status {
  font-size: 0.7rem;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  text-transform: capitalize;
}

.section-status--planned { background: var(--line); color: var(--muted); }
.section-status--draft { background: var(--warm-soft); color: var(--warm); }
.section-status--complete { background: var(--success-soft); color: var(--success); }

.section-content {
  margin-top: 6px;
  font-size: 0.85rem;
  color: var(--ink-soft);
  line-height: 1.45;
}

.empty-report {
  padding: var(--space-8) var(--space-4);
  text-align: center;
  color: var(--muted-soft);
  font-size: 0.9rem;
  border: 1px dashed var(--line-strong);
  border-radius: var(--radius);
}

@media (max-width: 600px) {
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .report-body-wrapper {
    padding: var(--space-4);
  }
}
</style>
