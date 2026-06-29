<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { renderChatMarkdown } from '../utils/markdownIt'
import type { StartupUpdateCheckResponse } from '../api/update'
import { getStartupUpdateCheck, setIgnoredUpdateTag } from '../api/update'
import { useUiStore } from '../stores'

const uiStore = useUiStore()
const startupUpdate = ref<StartupUpdateCheckResponse | null>(null)
const ignoring = ref(false)
const checking = ref(false)

const renderedNotes = computed(() => {
  const notes = startupUpdate.value?.releaseNotes?.trim()
  return renderChatMarkdown(notes || '本次 release 暂无可展示的更新说明。')
})

let startupTimerId: number | null = null

async function runStartupCheck() {
  if (checking.value) return
  checking.value = true
  try {
    const result = await getStartupUpdateCheck()
    startupUpdate.value = result.shouldNotify && result.tagName ? result : null
  } catch (error) {
    console.debug('[update] startup check failed', error)
  } finally {
    checking.value = false
  }
}

async function ignoreRelease() {
  const tag = startupUpdate.value?.tagName
  if (!tag || ignoring.value) return
  ignoring.value = true
  try {
    await setIgnoredUpdateTag(tag)
    startupUpdate.value = null
  } catch (error) {
    console.debug('[update] ignore release failed', error)
  } finally {
    ignoring.value = false
  }
}

function openUpdateFlow() {
  uiStore.requestOpenSettings('global')
  startupUpdate.value = null
}

onMounted(() => {
  startupTimerId = window.setTimeout(() => {
    void runStartupCheck()
  }, 40000)
})

onBeforeUnmount(() => {
  if (startupTimerId !== null) {
    window.clearTimeout(startupTimerId)
    startupTimerId = null
  }
})
</script>

<template>
  <Transition name="startup-update-card">
    <div
      v-if="startupUpdate"
      class="fixed right-4 bottom-4 z-[120] w-[min(560px,calc(100vw-2rem))] max-h-[min(40vh,316px)] flex flex-col min-h-0 overflow-hidden pointer-events-auto"
    >
      <section class="theme-panel-bg backdrop-blur-[var(--glass-blur-panel)] backdrop-saturate-[1.8] border border-[var(--color-border)] shadow-glass-panel rounded-2xl overflow-hidden flex flex-col flex-1 min-h-0">
        <header class="px-4 pt-4 pb-3 border-b border-[var(--color-border-subtle)] shrink-0 flex items-start justify-between gap-3">
          <div class="min-w-0">
            <div class="inline-flex items-center gap-2 rounded-full border border-[var(--color-brand-a30)] bg-[var(--color-brand-a10)] px-2.5 py-1 text-[11px] font-medium tracking-[0.08em] uppercase text-[var(--color-brand-fg-soft)]">
              启动检查
            </div>
            <h2 class="mt-3 text-base font-semibold text-[var(--color-text)]">发现新版本 {{ startupUpdate.latestVersion }}</h2>
            <p class="mt-1 text-sm text-[var(--color-text-secondary)]">
              当前版本 {{ startupUpdate.currentVersion }}，可在设置中的更新流程里继续安装。
            </p>
          </div>
        </header>

        <div
          class="px-4 py-3 flex-1 min-h-0 overflow-y-auto overscroll-contain startup-update-markdown prose prose-invert prose-sm max-w-none"
          v-html="renderedNotes"
        ></div>

        <footer class="px-4 py-3 border-t border-[var(--color-border-subtle)] shrink-0 flex items-center justify-end gap-2">
          <button type="button" class="btn btn-sm btn-secondary" :disabled="ignoring" @click="ignoreRelease">
            {{ ignoring ? '处理中...' : '忽略' }}
          </button>
          <button type="button" class="btn btn-sm btn-primary" @click="openUpdateFlow">更新</button>
        </footer>
      </section>
    </div>
  </Transition>
</template>

<style scoped>
.startup-update-card-enter-active,
.startup-update-card-leave-active {
  transition: opacity 180ms ease, transform 180ms ease;
}

.startup-update-card-enter-from,
.startup-update-card-leave-to {
  opacity: 0;
  transform: translateY(8px);
}

.startup-update-markdown :deep(p),
.startup-update-markdown :deep(ul),
.startup-update-markdown :deep(ol),
.startup-update-markdown :deep(pre),
.startup-update-markdown :deep(blockquote) {
  margin: 0 0 0.75rem;
}

.startup-update-markdown :deep(*:last-child) {
  margin-bottom: 0;
}

.startup-update-markdown :deep(p),
.startup-update-markdown :deep(li),
.startup-update-markdown :deep(blockquote) {
  color: var(--color-text-secondary);
  font-size: 0.875rem;
  line-height: 1.6;
}

.startup-update-markdown :deep(a) {
  color: var(--color-brand-fg-soft);
}

.startup-update-markdown :deep(code) {
  background: var(--color-surface-muted);
  border: 1px solid var(--color-border-subtle);
  border-radius: 0.375rem;
  color: var(--color-text);
  padding: 0.1rem 0.35rem;
}

.startup-update-markdown :deep(pre) {
  background: color-mix(in srgb, var(--color-surface-overlay) 70%, transparent);
  border: 1px solid var(--color-border-subtle);
  border-radius: 0.75rem;
  color: var(--color-text);
  overflow-x: auto;
  padding: 0.75rem;
}

.startup-update-markdown :deep(pre code) {
  background: transparent;
  border: 0;
  padding: 0;
}

.startup-update-markdown :deep(ul),
.startup-update-markdown :deep(ol) {
  padding-left: 1.1rem;
}
</style>