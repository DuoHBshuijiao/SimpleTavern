<script setup lang="ts">
/**
 * 全局通知宿主：Teleport 到 body，与 useNotify 共用队列。
 * 流式错误仍由 ChatPage 的 useErrorStack + ErrorModal 处理（方案 A）。
 */
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useNotifyHost } from '../composables/useNotify'
import { useSettingsStore } from '../stores'
import { normalizeThemeId } from '../types/models'

const settingsStore = useSettingsStore()
/** Teleport 到 body 后与 #app 同级，显式绑定 data-theme，保证语义色与 App 根一致 */
const appThemeId = computed(() => normalizeThemeId(settingsStore.settings?.themeId))

const { current, dismissAlert, confirmYes, confirmNo } = useNotifyHost()
const primaryButtonRef = ref<HTMLButtonElement | null>(null)

const headerTitle = computed(() => {
  const c = current.value
  if (!c) return ''
  if (c.kind === 'alert') return c.title || '提示'
  return c.title || '确认'
})

function onBackdropClick() {
  const c = current.value
  if (!c) return
  if (c.kind === 'alert') dismissAlert()
  else confirmNo()
}

function closeCurrentFromKeyboard() {
  const c = current.value
  if (!c) return
  if (c.kind === 'alert') dismissAlert()
  else confirmNo()
}

function handleKeydown(event: KeyboardEvent) {
  if (!current.value || event.key !== 'Escape') return
  event.preventDefault()
  closeCurrentFromKeyboard()
}

watch(current, async (item) => {
  if (!item) return
  await nextTick()
  primaryButtonRef.value?.focus()
})

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown)
})
</script>

<template>
  <Teleport to="body">
    <div
      v-if="current"
      class="app-notify-host fixed inset-0 z-notification flex justify-center items-start px-4 pointer-events-auto"
      :data-theme="appThemeId"
    >
      <div
        class="app-notify-backdrop absolute inset-0"
        aria-hidden="true"
        @click="onBackdropClick"
      />
      <div
        class="app-notify-panel relative mt-[min(15vh,6rem)] w-[min(560px,calc(100vw-2rem))] max-h-[min(70vh,520px)] flex flex-col rounded-2xl border border-[var(--color-border)] overflow-hidden"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="`app-notify-title-${current.id}`"
        @click.stop
      >
        <div class="px-4 pt-4 pb-2 border-b border-[var(--color-border-subtle)] shrink-0">
          <h2 :id="`app-notify-title-${current.id}`" class="text-base font-semibold text-[var(--color-text)]">
            {{ headerTitle }}
          </h2>
        </div>

        <div class="px-4 py-3 overflow-y-auto flex-1 min-h-0">
          <pre
            class="text-sm leading-relaxed text-[var(--color-text)] whitespace-pre-wrap break-words font-sans"
            >{{ current.message }}</pre
          >
        </div>

        <div
          v-if="current.kind === 'alert'"
          class="px-4 py-3 flex justify-end gap-2 border-t border-[var(--color-border-subtle)] shrink-0"
        >
          <button ref="primaryButtonRef" type="button" class="btn btn-sm btn-primary" @click="dismissAlert">确定</button>
        </div>
        <div
          v-else
          class="px-4 py-3 flex justify-end gap-2 border-t border-[var(--color-border-subtle)] shrink-0"
        >
          <button type="button" class="btn btn-sm btn-secondary" @click="confirmNo">取消</button>
          <button
            v-if="current.variant === 'danger'"
            ref="primaryButtonRef"
            type="button"
            class="btn btn-sm btn-danger"
            @click="confirmYes"
          >
            确定
          </button>
          <button v-else ref="primaryButtonRef" type="button" class="btn btn-sm btn-primary" @click="confirmYes">确定</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
/*
 * 渲染链说明（与 .modal 的差异）：
 * - .modal：遮罩为 --color-overlay + opacity:0.6，内容区用 --color-surface-overlay（~20% 暗叠层）叠在中等灰底上，能看出玻璃层。
 * - 本组件：遮罩为 --color-overlay-heavy（~70% 黑），若面板仍用 --color-surface-overlay，则「20% 叠层 + 重黑底」几乎合成一整块黑玻璃，主题色不可见。
 * 因此面板改用随 data-theme 的抬升表面做半透明纯色，而非 surface-overlay。
 */
.app-notify-backdrop {
  background-color: var(--color-overlay-heavy);
  backdrop-filter: blur(var(--blur-light));
  -webkit-backdrop-filter: blur(var(--blur-light));
}

.app-notify-panel {
  background-color: color-mix(in srgb, var(--color-surface-elevated) 88%, transparent);
  background-image: none;
  backdrop-filter: blur(var(--blur-light));
  -webkit-backdrop-filter: blur(var(--blur-light));
  box-shadow: var(--shadow-heavy);
}
</style>
