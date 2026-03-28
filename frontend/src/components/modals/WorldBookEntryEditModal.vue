<script setup lang="ts">
/**
 * 单条世界书条目编辑：正文 / 正则分区、与后端 WorldBookEntry 校验一致。
 */
import { ref, watch } from 'vue'
import { X } from 'lucide-vue-next'
import type { WorldBookEntry } from '../../types/models'
import { validateWorldBookEntry } from '../../utils/worldBookValidation'

const props = defineProps<{
  show: boolean
  entry: WorldBookEntry | null
}>()

const emit = defineEmits<{
  'update:show': [boolean]
  apply: [WorldBookEntry]
}>()

const draft = ref<WorldBookEntry | null>(null)
const localError = ref('')
const testText = ref('')
const testResult = ref<string | null>(null)

watch(
  () => [props.show, props.entry] as const,
  ([open, ent]) => {
    if (open && ent) {
      draft.value = JSON.parse(JSON.stringify(ent)) as WorldBookEntry
      localError.value = ''
      testText.value = ''
      testResult.value = null
    }
    if (!open) {
      draft.value = null
    }
  },
  { immediate: true },
)

function tryMatch() {
  testResult.value = null
  if (!draft.value) return
  const pattern = (draft.value.regex || '').trim()
  if (!pattern) {
    testResult.value = '请先填写正则'
    return
  }
  try {
    const re = new RegExp(pattern)
    const text = testText.value
    const m = text.match(re)
    testResult.value = m ? `匹配：${JSON.stringify(m[0])}` : '无匹配（试匹配为 JavaScript 正则，与 Python re 在少数边界上可能不同）'
  } catch (e) {
    testResult.value = e instanceof Error ? e.message : String(e)
  }
}

function apply() {
  if (!draft.value) return
  const err = validateWorldBookEntry(draft.value)
  if (err) {
    localError.value = err
    return
  }
  localError.value = ''
  emit('apply', { ...draft.value })
  emit('update:show', false)
}

function close() {
  emit('update:show', false)
}
</script>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="show && draft" class="modal">
        <div class="modal-backdrop" @click="close"></div>
        <div
          class="modal-content w-[min(92vw,560px)] max-h-[90vh] theme-panel-bg border border-[var(--color-border)] rounded-2xl shadow-xl backdrop-saturate-[1.8]"
          style="backdrop-filter: blur(var(--blur-heavy)); -webkit-backdrop-filter: blur(var(--blur-heavy))"
        >
          <div class="modal-header shrink-0">
            <h3 class="modal-title">编辑条目</h3>
            <button type="button" class="modal-close" aria-label="关闭" @click="close">
              <X class="w-5 h-5" />
            </button>
          </div>
          <div class="modal-body overflow-y-auto custom-scrollbar min-h-0 space-y-4">
            <div
              v-if="localError"
              class="text-sm text-[var(--color-error)] bg-[var(--color-surface-overlay)] border border-[var(--color-border)] rounded-lg px-3 py-2"
            >
              {{ localError }}
            </div>

            <div class="space-y-1.5">
              <label class="text-xs font-medium text-[var(--color-text-secondary)]">标题</label>
              <input v-model="draft.title" type="text" class="input w-full" placeholder="条目标题" />
            </div>

            <div class="flex items-center gap-3">
              <label class="flex items-center gap-2 text-sm text-[var(--color-text-secondary)] cursor-pointer">
                <input v-model="draft.enabled" type="checkbox" class="rounded border-[var(--color-border)]" />
                启用
              </label>
            </div>

            <p class="text-xs text-[var(--color-text-muted)]">
              扫描深度与插入深度在「当前会话 → 世界书顺序」中按每本书单独设置，不再保存在条目内。
            </p>

            <div class="space-y-2 border-t border-[var(--color-border-subtle)] pt-4">
              <div class="text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wider">正则表达式</div>
              <textarea
                v-model="draft.regex"
                rows="4"
                class="input textarea w-full font-mono text-sm resize-y min-h-[96px]"
                placeholder="例如 (?i)keyword"
              />
            </div>

            <div class="space-y-2">
              <div class="text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wider">正文内容</div>
              <textarea
                v-model="draft.content"
                rows="8"
                class="input textarea w-full text-sm resize-y min-h-[160px]"
                placeholder="匹配后注入的文本"
              />
            </div>

            <div class="space-y-2 rounded-lg border border-[var(--color-border-subtle)] bg-surface-muted p-3">
              <div class="text-xs text-[var(--color-text-muted)]">试匹配（可选，浏览器 RegExp，与 Python re 可能有细微差异）</div>
              <textarea v-model="testText" rows="2" class="input textarea w-full text-sm" placeholder="测试文本" />
              <div class="flex items-center gap-2">
                <button type="button" class="btn btn-sm btn-secondary" @click="tryMatch">试匹配</button>
                <span v-if="testResult" class="text-xs text-[var(--color-text-secondary)]">{{ testResult }}</span>
              </div>
            </div>
          </div>
          <div class="modal-footer shrink-0">
            <button type="button" class="btn btn-secondary" @click="close">取消</button>
            <button type="button" class="btn btn-primary" @click="apply">确定</button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.custom-scrollbar::-webkit-scrollbar {
  width: 4px;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background: var(--color-border, rgba(255, 255, 255, 0.2));
  border-radius: 2px;
}
</style>
