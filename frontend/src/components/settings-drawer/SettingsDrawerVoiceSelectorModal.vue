<script setup lang="ts">
import { Check, X } from 'lucide-vue-next'
import type { ApiPresetVoice } from '../../types/models'

const show = defineModel<boolean>('show', { required: true })
const query = defineModel<string>('query', { default: '' })

defineProps<{
  candidates: ApiPresetVoice[]
  selected: Set<string>
}>()

const emit = defineEmits<{
  toggle: [voiceId: string]
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
        class="glass-l6 relative m-4 flex max-h-[85vh] min-h-0 w-full max-w-lg min-w-[400px] flex-col rounded-2xl shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="voice-selector-title"
      >
        <div class="flex items-center justify-between rounded-t-2xl border-b border-[var(--color-border)] bg-surface-muted p-4">
          <h3 id="voice-selector-title" class="text-[var(--color-text)]">选择音色</h3>
          <button
            type="button"
            class="icon-button min-h-11 min-w-11 shrink-0 touch-manipulation"
            aria-label="关闭音色选择弹窗"
            @click="show = false"
          >
            <X class="h-5 w-5" />
          </button>
        </div>

        <div class="border-b border-[var(--color-border)] bg-transparent p-3">
          <input
            v-model="query"
            placeholder="筛选音色（名称、ID、类型）..."
            class="input w-full"
            autofocus
          />
        </div>

        <div class="drawer-scroll min-h-0 flex-1 overflow-y-auto bg-transparent p-2">
          <div
            v-if="candidates.length === 0"
            class="py-8 text-center text-sm text-[var(--color-text-muted)]"
          >
            未找到音色
          </div>
          <div v-else class="space-y-1">
            <div
              v-for="v in candidates"
              :key="v.voiceId"
              class="flex min-h-11 cursor-pointer items-center gap-3 rounded-lg px-3 py-2 transition-colors hover:bg-surface-muted touch-manipulation"
              @click="emit('toggle', v.voiceId)"
            >
              <div
                class="flex h-4 w-4 shrink-0 items-center justify-center rounded border transition-colors"
                :class="selected.has(v.voiceId) ? 'border-brand bg-brand' : 'border-[var(--color-border)]'"
              >
                <Check v-if="selected.has(v.voiceId)" class="h-2.5 w-2.5 text-on-brand" />
              </div>
              <div class="min-w-0 flex-1">
                <div
                  class="truncate text-sm text-[var(--color-text-secondary)]"
                  :class="selected.has(v.voiceId) ? 'font-medium text-[var(--color-text)]' : ''"
                >
                  {{ v.name }}
                </div>
                <div class="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-[var(--color-text-muted)]">
                  <span class="truncate font-mono">{{ v.voiceId }}</span>
                  <span
                    class="shrink-0 rounded-full bg-surface-muted px-1.5 py-0.5 text-[10px] text-[var(--color-text-muted)]"
                  >{{ v.voiceType }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="flex items-center justify-between rounded-b-2xl border-t border-[var(--color-border)] bg-surface-muted p-4">
          <div class="text-xs text-[var(--color-text-muted)]">已选 {{ selected.size }} 个音色</div>
          <div class="flex gap-2">
            <button type="button" class="btn btn-secondary min-h-11" @click="show = false">取消</button>
            <button type="button" class="btn btn-primary min-h-11" @click="emit('confirm')">确认</button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>
