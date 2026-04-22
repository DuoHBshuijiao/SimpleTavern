<script setup lang="ts">
const props = defineProps<{
  show: boolean
  disabled?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:show', value: boolean): void
  (e: 'export', format: 'txt' | 'json' | 'jsonl' | 'character' | 'character_with_worldbooks'): void
}>()

function close() {
  emit('update:show', false)
}

function handleExport(format: 'txt' | 'json' | 'jsonl' | 'character' | 'character_with_worldbooks') {
  if (props.disabled) return
  emit('export', format)
}
</script>

<template>
  <Transition name="modal">
    <div v-if="show" class="modal">
      <!-- 背景模糊须用 Tailwind backdrop-*（见 README / glass.css：手写 backdrop-filter 经 esbuild 压缩可能失效） -->
      <div class="modal-backdrop backdrop-blur-[var(--blur-heavy)]" @click="close"></div>
      <div
        class="modal-content chat-modal-width-600-90 glass-panel theme-panel-bg backdrop-blur-[var(--blur-heavy)] backdrop-saturate-[1.8] border border-[var(--color-border)]"
      >
        <div class="modal-header border-b border-[var(--color-border-subtle)]">
          <h3 class="modal-title text-[var(--color-text)]">导出</h3>
          <button class="modal-close text-[var(--color-text-muted)] hover:text-[var(--color-text)]" @click="close">×</button>
        </div>
        <div class="modal-body">
          <div class="space-y-3" :class="disabled ? 'opacity-50 pointer-events-none' : ''">
            <div class="rounded-xl border border-[var(--color-border-subtle)] bg-[var(--color-surface-muted)] p-4 text-sm text-[var(--color-text-muted)]">
              选择导出格式
            </div>
            <button
              class="w-full rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-overlay)] px-4 py-3 text-left text-[var(--color-text)] transition-colors hover:bg-[var(--color-surface-hover)]"
              @click="handleExport('txt')"
            >
              导出 TXT
            </button>
            <button
              class="w-full rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-overlay)] px-4 py-3 text-left text-[var(--color-text)] transition-colors hover:bg-[var(--color-surface-hover)]"
              @click="handleExport('json')"
            >
              导出 JSON
            </button>
            <button
              class="w-full rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-overlay)] px-4 py-3 text-left text-[var(--color-text)] transition-colors hover:bg-[var(--color-surface-hover)]"
              @click="handleExport('jsonl')"
            >
              导出 JSONL（精简）
            </button>
            <button
              class="w-full rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-overlay)] px-4 py-3 text-left text-[var(--color-text)] transition-colors hover:bg-[var(--color-surface-hover)]"
              @click="handleExport('character')"
            >
              导出角色（JSON）
            </button>
            <button
              class="w-full rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-overlay)] px-4 py-3 text-left text-[var(--color-text)] transition-colors hover:bg-[var(--color-surface-hover)]"
              @click="handleExport('character_with_worldbooks')"
            >
              导出角色+世界书（ZIP）
            </button>
          </div>
          <p v-if="disabled" class="mt-3 text-xs text-[var(--color-text-muted)]">请先选择或创建会话。</p>
        </div>
      </div>
    </div>
  </Transition>
</template>
