<script setup lang="ts">
import { Check, X } from 'lucide-vue-next'

const show = defineModel<boolean>('show', { required: true })
const query = defineModel<string>('query', { default: '' })

defineProps<{
  candidates: string[]
  selected: Set<string>
}>()

const emit = defineEmits<{
  toggle: [model: string]
  confirm: []
}>()
</script>

<template>
  <Teleport to="body">
    <div v-if="show" class="fixed inset-0 z-[var(--z-popover)] flex items-center justify-center">
      <div
        class="absolute inset-0 bg-overlay-heavy backdrop-blur-[var(--glass-blur-soft)]"
        @click="show = false"
      />
      <div
        class="glass-l6 relative m-4 flex max-h-[85vh] w-full min-w-[400px] max-w-lg flex-col rounded-2xl shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="model-selector-title"
      >
        <div class="flex items-center justify-between rounded-t-2xl border-b border-[var(--color-border)] bg-surface-muted p-4">
          <h3 id="model-selector-title" class="text-[var(--color-text)]">选择模型</h3>
          <button
            type="button"
            class="icon-button min-h-11 min-w-11 shrink-0 touch-manipulation"
            aria-label="关闭模型选择弹窗"
            @click="show = false"
          >
            <X class="h-5 w-5" />
          </button>
        </div>

        <div class="border-b border-[var(--color-border)] bg-transparent p-3">
          <input v-model="query" placeholder="筛选模型..." class="input w-full" autofocus />
        </div>

        <div class="drawer-scroll flex-1 overflow-y-auto bg-transparent p-2">
          <div
            v-if="candidates.length === 0"
            class="py-8 text-center text-sm text-[var(--color-text-muted)]"
          >
            未找到模型
          </div>
          <div v-else class="space-y-1">
            <div
              v-for="m in candidates"
              :key="m"
              class="flex min-h-11 cursor-pointer items-center gap-3 rounded-lg px-3 py-2 transition-colors hover:bg-surface-muted touch-manipulation"
              @click="emit('toggle', m)"
            >
              <div
                class="flex h-4 w-4 items-center justify-center rounded border transition-colors"
                :class="selected.has(m) ? 'border-brand bg-brand' : 'border-[var(--color-border)]'"
              >
                <Check v-if="selected.has(m)" class="h-2.5 w-2.5 text-on-brand" />
              </div>
              <span
                class="text-sm text-[var(--color-text-secondary)]"
                :class="selected.has(m) ? 'font-medium text-[var(--color-text)]' : ''"
              >{{ m }}</span>
            </div>
          </div>
        </div>

        <div class="flex items-center justify-between rounded-b-2xl border-t border-[var(--color-border)] bg-surface-muted p-4">
          <div class="text-xs text-[var(--color-text-muted)]">已选 {{ selected.size }} 个模型</div>
          <div class="flex gap-2">
            <button type="button" class="btn btn-secondary min-h-11" @click="show = false">取消</button>
            <button type="button" class="btn btn-primary min-h-11" @click="emit('confirm')">确认</button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>
