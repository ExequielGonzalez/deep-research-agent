<script setup lang="ts">
import { onMounted } from 'vue'
import { RouterView, useRouter, useRoute } from 'vue-router'
import { useResearchStore } from '@/stores/useResearchStore'
import { useSettingsStore } from '@/stores/useSettingsStore'

const router = useRouter()
const route = useRoute()
const researchStore = useResearchStore()
const settingsStore = useSettingsStore()

onMounted(async () => {
  await Promise.all([
    researchStore.fetchRuns(),
    settingsStore.fetchSettings(),
    settingsStore.fetchConfig(),
    settingsStore.fetchModels(),
  ])
})
</script>

<template>
  <div class="app-shell">
    <!-- Sidebar Navigation -->
    <aside class="sidebar">
      <div class="sidebar-header">
        <div class="brand-mark">DR</div>
        <span class="text-eyebrow">Deep Research</span>
        <h1 class="brand-title">Deep Research<br />Agent</h1>
        <p class="brand-description">
          Launch deep research investigations, track progress in real time,
          and read the final synthesized report.
        </p>
      </div>

      <nav class="sidebar-nav" aria-label="Main navigation">
        <button
          class="nav-item"
          :class="{ active: route.name === 'research' }"
          @click="router.push('/')"
          aria-current="page"
        >
          <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <span>Research</span>
        </button>
        <button
          class="nav-item"
          :class="{ active: route.name === 'settings' }"
          @click="router.push('/settings')"
          aria-current="page"
        >
          <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
            <circle cx="12" cy="12" r="3" />
          </svg>
          <span>Settings</span>
        </button>
      </nav>

      <div class="sidebar-footer">
        <span class="version-badge">v0.1.0</span>
      </div>
    </aside>

    <!-- Main Content Area -->
    <main class="main-content">
      <RouterView v-slot="{ Component }">
        <transition name="page" mode="out-in">
          <component :is="Component" />
        </transition>
      </RouterView>
    </main>
  </div>
</template>

<style scoped>
/* ── App Shell Layout ──────────────────────────────────────────────── */

.app-shell {
  display: flex;
  min-height: 100dvh;
}

/* ── Sidebar ───────────────────────────────────────────────────────── */

.sidebar {
  width: 280px;
  min-width: 280px;
  display: flex;
  flex-direction: column;
  background: var(--surface);
  border-right: 1px solid var(--line);
  padding: var(--space-6) var(--space-5);
  position: sticky;
  top: 0;
  height: 100dvh;
  overflow-y: auto;
}

.sidebar-header {
  margin-bottom: var(--space-8);
}

.brand-mark {
  width: 44px;
  height: 44px;
  border-radius: var(--radius);
  display: grid;
  place-items: center;
  font-family: var(--font-mono);
  font-weight: 700;
  font-size: 1rem;
  color: white;
  background: linear-gradient(135deg, var(--accent) 0%, var(--accent-bright) 100%);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.3);
  margin-bottom: var(--space-4);
}

.brand-title {
  font-size: 1.3rem;
  line-height: 1.2;
  margin-top: var(--space-1);
  color: var(--ink);
}

.brand-description {
  margin-top: var(--space-3);
  font-size: 0.875rem;
  line-height: 1.55;
  color: var(--muted);
}

/* ── Navigation ────────────────────────────────────────────────────── */

.sidebar-nav {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  flex: 1;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border: none;
  border-radius: var(--radius);
  background: transparent;
  color: var(--muted);
  font-family: var(--font-body);
  font-size: 0.95rem;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
  text-align: left;
  width: 100%;
}

.nav-item:hover {
  background: var(--accent-soft);
  color: var(--accent-strong);
}

.nav-item.active {
  background: var(--accent-soft);
  color: var(--accent-strong);
}

.nav-icon {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
}

/* ── Sidebar Footer ────────────────────────────────────────────────── */

.sidebar-footer {
  padding-top: var(--space-4);
  border-top: 1px solid var(--line);
}

.version-badge {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  color: var(--muted-soft);
}

/* ── Main Content ──────────────────────────────────────────────────── */

.main-content {
  flex: 1;
  min-width: 0;
  padding: var(--space-6);
  overflow-y: auto;
}

/* ── Page Transitions ──────────────────────────────────────────────── */

.page-enter-active,
.page-leave-active {
  transition: opacity var(--transition), transform var(--transition);
}

.page-enter-from {
  opacity: 0;
  transform: translateY(8px);
}

.page-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

/* ── Responsive ────────────────────────────────────────────────────── */

@media (max-width: 768px) {
  .app-shell {
    flex-direction: column;
  }

  .sidebar {
    width: 100%;
    min-width: 0;
    height: auto;
    position: static;
    padding: var(--space-4);
    flex-direction: row;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-3);
    border-right: none;
    border-bottom: 1px solid var(--line);
  }

  .sidebar-header {
    margin-bottom: 0;
    display: flex;
    align-items: center;
    gap: var(--space-3);
    flex: 1;
  }

  .brand-mark {
    margin-bottom: 0;
    width: 36px;
    height: 36px;
    font-size: 0.85rem;
  }

  .brand-title {
    font-size: 1rem;
  }

  .brand-description,
  .sidebar-footer {
    display: none;
  }

  .sidebar-nav {
    flex-direction: row;
    flex: 0 0 auto;
  }

  .main-content {
    padding: var(--space-4);
  }
}
</style>
