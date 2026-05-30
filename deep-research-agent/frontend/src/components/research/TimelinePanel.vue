<script setup lang="ts">
import { computed } from 'vue'
import type { ResearchRun, ResearchGraphState } from '@/types'

const props = defineProps<{
  run: ResearchRun
}>()

const graph = computed<ResearchGraphState>(() => {
  return (props.run.state ?? {}) as ResearchGraphState
})

interface TimelineSection {
  title: string
  kind: string
  groups: TimelineGroup[]
  count: number
}

interface TimelineGroup {
  key: string
  title: string
  items: string[]
}

function createSection(title: string, kind: string): TimelineSection {
  return { title, kind, groups: [], count: 0 }
}

function ensureGroup(section: TimelineSection, key: string, title: string): TimelineGroup {
  let group = section.groups.find((g) => g.key === key)
  if (!group) {
    group = { key, title, items: [] }
    section.groups.push(group)
  }
  return group
}

function classifyNote(note: string, sectionKind: string): { key: string; title: string } {
  const n = note.toLowerCase()
  if (n.includes('retrieved ') || n.includes('no search hits') || n.includes('additional search'))
    return { key: 'search', title: 'Search' }
  if (n.includes('extract') || n.includes('extractable content') || n.includes('evidence item'))
    return { key: 'extraction', title: 'Extraction' }
  if (n.includes('knowledge gap') || n.includes('follow-up task'))
    return { key: 'reflection', title: 'Reflection' }
  if (n.includes('plan approval') || n.includes('plan review') || n.includes('re-planning'))
    return { key: 'review', title: 'Review' }
  if (n.includes('sufficiency review') || n.includes('human review'))
    return { key: 'review', title: 'Review' }
  if (n.includes('synthesized final report') || n.includes('run cancelled') || n.includes('run failed'))
    return { key: 'result', title: 'Result' }
  if (sectionKind === 'iteration')
    return { key: 'reflection', title: 'Reflection' }
  return { key: 'overview', title: sectionKind === 'planning' ? 'Plan' : 'Summary' }
}

const sections = computed<TimelineSection[]>(() => {
  const notes = graph.value.notes ?? []
  if (!notes.length) return []

  const result: TimelineSection[] = []
  let planningSection = createSection('Plan & Setup', 'planning')
  let current = planningSection
  let currentIterationLabel: string | null = null
  result.push(planningSection)

  for (const note of notes) {
    const iterationMatch = note.match(/^Starting research iteration (\d+) of (\d+)\./i)
    if (iterationMatch) {
      currentIterationLabel = `Iteration ${iterationMatch[1]} of ${iterationMatch[2]}`
      current = createSection(currentIterationLabel, 'iteration')
      result.push(current)
      ensureGroup(current, 'overview', 'Start').items.push(note)
      continue
    }

    const n = note.toLowerCase()
    if (n.includes('synthesized final report') || n.includes('run cancelled')) {
      const last = result[result.length - 1]
      if (!last || last.kind !== 'report') {
        current = createSection('Closing', 'report')
        result.push(current)
      }
      ensureGroup(current, 'result', 'Result').items.push(note)
      continue
    }

    if (n.includes('awaiting human') || n.includes('received sufficiency')) {
      if (current.kind !== 'review') {
        current = createSection('Human Review', 'review')
        result.push(current)
      }
      ensureGroup(current, 'review', 'Checkpoint').items.push(note)
      continue
    }

    if (n.includes('plan approval') || n.includes('plan review')) {
      current = planningSection
    }

    const group = classifyNote(note, current.kind)
    ensureGroup(current, group.key, group.title).items.push(note)
  }

  return result.filter((s) => s.count > 0)
})
</script>

<template>
  <div class="timeline-panel">
    <div class="text-eyebrow" style="margin-bottom: var(--space-3)">Timeline</div>

    <div v-if="sections.length === 0" class="empty-state animate-fade-in">
      <p>Timeline will fill as the graph progresses.</p>
    </div>

    <div v-else class="timeline-sections">
      <details
        v-for="(section, idx) in sections"
        :key="idx"
        class="timeline-group"
        :open="idx >= sections.length - 2"
      >
        <summary class="timeline-summary">
          <div>
            <span class="group-title">{{ section.title }}</span>
            <p class="group-meta">
              {{ section.groups.map(g => `${g.title} ${g.items.length}`).join(' · ') }}
            </p>
          </div>
          <span class="group-count">{{ section.count }}</span>
        </summary>
        <div class="timeline-body">
          <div v-for="group in section.groups" :key="group.key" class="timeline-subgroup">
            <h4 class="subgroup-title">{{ group.title }}</h4>
            <div class="subgroup-items">
              <div v-for="(item, i) in group.items" :key="i" class="timeline-item">
                <div class="timeline-dot" />
                <p>{{ item }}</p>
              </div>
            </div>
          </div>
        </div>
      </details>
    </div>
  </div>
</template>

<style scoped>
.timeline-panel {
  display: flex;
  flex-direction: column;
}

.timeline-sections {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.timeline-group {
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--surface-strong);
  overflow: hidden;
}

.timeline-group summary {
  list-style: none;
}

.timeline-group summary::-webkit-details-marker {
  display: none;
}

.timeline-summary {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  cursor: pointer;
  transition: background var(--transition-fast);
}

.timeline-summary:hover {
  background: var(--accent-soft);
}

.timeline-group[open] .timeline-summary {
  border-bottom: 1px solid var(--line);
  background: var(--accent-soft);
}

.group-title {
  font-weight: 600;
  font-size: 0.9rem;
  line-height: 1.3;
}

.group-meta {
  font-size: 0.78rem;
  color: var(--muted);
  margin-top: 4px;
}

.group-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 22px;
  height: 22px;
  padding: 0 6px;
  border-radius: var(--radius-full);
  background: var(--line);
  font-size: 0.72rem;
  font-weight: 600;
  font-family: var(--font-mono);
  color: var(--muted);
}

.timeline-body {
  padding: var(--space-3) var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.timeline-subgroup {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.subgroup-title {
  font-family: var(--font-body);
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--muted);
}

.subgroup-items {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.timeline-item {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  font-size: 0.85rem;
  line-height: 1.45;
  color: var(--ink-soft);
}

.timeline-dot {
  flex-shrink: 0;
  width: 6px;
  height: 6px;
  margin-top: 8px;
  border-radius: 50%;
  background: var(--accent);
  opacity: 0.6;
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
