<script setup lang="ts">
defineProps<{
  current: number
  max: number
  label?: string
}>()
</script>

<template>
  <div class="progress-bar" role="progressbar" :aria-valuenow="current" :aria-valuemin="0" :aria-valuemax="max">
    <div class="progress-track">
      <div
        class="progress-fill"
        :style="{ width: `${Math.min((current / Math.max(max, 1)) * 100, 100)}%` }"
      />
    </div>
    <span class="progress-label">
      <slot>
        {{ label }} {{ current }} / {{ max }}
      </slot>
    </span>
  </div>
</template>

<style scoped>
.progress-bar {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.progress-track {
  height: 6px;
  background: var(--line);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--accent) 0%, var(--accent-bright) 100%);
  border-radius: var(--radius-full);
  transition: width 0.4s cubic-bezier(0.22, 1, 0.36, 1);
}

.progress-label {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--muted);
  font-family: var(--font-mono);
}
</style>
