<script setup lang="ts">
/**
 * 单条世界书条目编辑：正文 / 正则分区、与后端 WorldBookEntry 校验一致。
 */
import { ref, watch } from 'vue'
import { X } from 'lucide-vue-next'
import type { WorldBookEntry } from '../../types/models'
import SettingsField from '../settings-drawer/SettingsField.vue'
import SettingsSwitch from '../settings-drawer/SettingsSwitch.vue'
import SettingsHint from '../settings-drawer/SettingsHint.vue'
import { buildRegexFromInput } from '../../utils/regexCompat'
import { validateWorldBookEntry } from '../../utils/worldBookValidation'
import { useDialogBehavior } from '../../composables/useDialogBehavior'
import { dialogAria } from '../../utils/uiPrimitives'

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
    const re = buildRegexFromInput(pattern)
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

const titleId = 'world-book-entry-edit-title'
const dialogAttrs = dialogAria(titleId)
const { dialogRef } = useDialogBehavior(() => props.show && !!props.entry, close)
void dialogRef
</script>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="show && draft" class="modal">
        <div class="modal-backdrop backdrop-blur-[var(--glass-blur-soft)]" @click="close"></div>
        <div
          ref="dialogRef"
          v-bind="dialogAttrs"
          tabindex="-1"
          class="modal-content modal-surface w-[min(92vw,560px)] max-h-[90vh]"
        >
          <div class="modal-header shrink-0">
            <h3 :id="titleId" class="modal-title">编辑条目</h3>
            <button type="button" class="modal-close" aria-label="关闭" @click="close">
              <X class="w-5 h-5" />
            </button>
          </div>
          <div class="modal-body custom-scrollbar min-h-0">
            <div class="settings-group">
              <div v-if="localError" role="alert" class="settings-readout text-[var(--color-error)]">
                {{ localError }}
              </div>
              <SettingsField label="标题">
                <input v-model="draft.title" type="text" class="input w-full" placeholder="条目标题" />
              </SettingsField>
              <SettingsSwitch
                label="启用"
                :model-value="draft.enabled"
                more="扫描深度和插入深度在「当前会话 → 世界书顺序」里按每本书设置，不保存在条目里。"
                @update:model-value="draft.enabled = $event"
              />
              <SettingsField label="正则表达式">
                <textarea
                  v-model="draft.regex"
                  rows="4"
                  class="input textarea w-full font-mono text-sm resize-y min-h-[96px]"
                  placeholder="例如 keyword 或 /keyword/iu"
                />
              </SettingsField>
              <SettingsField label="正文内容">
                <textarea
                  v-model="draft.content"
                  rows="8"
                  class="input textarea w-full text-sm resize-y min-h-[160px]"
                  placeholder="匹配后注入的文本"
                />
              </SettingsField>
            </div>

            <div class="settings-group">
              <div class="settings-field-head">
                <div class="settings-group-title">试匹配</div>
                <button type="button" class="btn btn-xs btn-secondary" @click="tryMatch">试匹配</button>
              </div>
              <textarea v-model="testText" rows="2" class="input textarea w-full text-sm" placeholder="测试文本" />
              <div v-if="testResult" class="settings-readout break-words">{{ testResult }}</div>
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
