<script setup lang="ts">
import type { SourceRecord } from '@/types'

defineProps<{
  sources: SourceRecord[]
}>()

function truncateUrl(url: string, max = 50): string {
  if (url.length <= max) return url
  return url.slice(0, max - 3) + '...'
}
</script>

<template>
  <div class="sources-panel">
    <div class="panel-header">
      <span class="text-eyebrow">Sources</span>
      <span class="count-badge">{{ sources.length }}</span>
    </div>

    <div v-if="sources.length === 0" class="empty-state">
      <p>Sources appear after the search phase.</p>
    </div>

    <div v-else class="sources-list">
      <article
        v-for="source in sources.slice(0, 10)"
        :key="source.source_id"
        class="source-card animate-fade-in"
      >
        <h4 class="source-title">{{ source.title }}</h4>
        <a
          :href="source.url"
          target="_blank"
          rel="noopener noreferrer"
          class="source-url text-mono"
        >
          {{ truncateUrl(source.url) }}
          <svg class="external-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6M15 3h6v6M10 14L21 3" />
          </svg>
        </a>
        <p v-if="source.snippet" class="source-snippet">{{ source.snippet }}</p>
        <div class="source-meta">
          <span class="source-type">{{ source.source_type }}</span>
          <span class="source-provider">{{ source.provider }}</span>
        </div>
      </article>
    </div>
  </div>
</template>

<style scoped>
.sources-panel {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.count-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 24px;
  height: 24px;
  padding: 0 8px;
  border-radius: var(--radius-full);
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 0.78rem;
  font-weight: 700;
  font-family: var(--font-mono);
}

.sources-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.source-card {
  padding: var(--space-3) var(--space-4);
  background: var(--surface-strong);
  border: 1px solid var(--line);
  border-radius: var(--radius);
}

.source-title {
  font-family: var(--font-body);
  font-size: 0.9rem;
  font-weight: 600;
  line-height: 1.35;
  color: var(--ink);
  margin-bottom: 4px;
}

.source-url {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 0.78rem;
  word-break: break-all;
}

.external-icon {
  width: 12px;
  height: 12px;
  flex-shrink: 0;
}

.source-snippet {
  font-size: 0.82rem;
  color: var(--ink-soft);
  margin-top: 6px;
  line-height: 1.45;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.source-meta {
  display: flex;
  gap: var(--space-2);
  margin-top: var(--space-2);
}

.source-type,
.source-provider {
  font-size: 0.7rem;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  background: var(--line);
  color: var(--muted);
  text-transform: capitalize;
}

.empty-state {
  padding: var(--space-6) var(--space-4);
  text-align: center;
  color: var(--muted-soft);
  font-size: 0.9rem;
  border: 1px dashed var(--line-strong);
  border-radius: var(--radius);
}
</style>
