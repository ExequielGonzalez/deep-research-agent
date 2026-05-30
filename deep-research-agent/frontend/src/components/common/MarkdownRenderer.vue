<script setup lang="ts">
import { computed } from 'vue'
import { marked } from 'marked'

const props = defineProps<{
  content: string
}>()

const rendered = computed(() => {
  if (!props.content) return ''
  marked.setOptions({
    breaks: true,
    gfm: true,
  })
  return marked.parse(props.content)
})
</script>

<template>
  <div
    class="markdown-rendered report-body"
    v-html="rendered"
  />
</template>

<style scoped>
.markdown-rendered :deep(*) {
  max-width: 100%;
}
</style>
