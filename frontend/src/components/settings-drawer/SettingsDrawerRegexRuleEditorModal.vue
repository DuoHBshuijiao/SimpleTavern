<script setup lang="ts">
import { X } from 'lucide-vue-next'
import ModernSelect from '../ModernSelect.vue'
import ThemedRadioTags from '../ThemedRadioTags.vue'
import SettingsField from './SettingsField.vue'
import { useDialogBehavior } from '../../composables/useDialogBehavior'
import { dialogAria } from '../../utils/uiPrimitives'
import type { ChatContentRegexRule } from '../../types/models'

export type RegexTrialSourceMode = 'manual' | 'latest_assistant'

export interface RegexTrialResultView {
  beforeText: string
  afterText: string
  displayText: string
  changed: boolean
  extractedItems: Array<{ value: string; matchedText: string; ruleId: string }>
}

const show = defineModel<boolean>('show', { required: true })
const draft = defineModel<ChatContentRegexRule | null>('draft', { required: true })
const trialSourceMode = defineModel<RegexTrialSourceMode>('trialSourceMode', { default: 'manual' })
const trialManualText = defineModel<string>('trialManualText', { default: '' })

defineProps<{
  trialResult: RegexTrialResultView | null
  trialSourceOptions: ReadonlyArray<{ label: string; value: RegexTrialSourceMode }>
}>()

const emit = defineEmits<{
  save: []
  'run-trial': []
}>()

const titleId = 'regex-editor-title'
const dialogAttrs = dialogAria(titleId)
// Esc 由设置抽屉统一处理：这里也关的话，抽屉那边看到弹窗已关，会把抽屉一起关掉
const { dialogRef } = useDialogBehavior(() => show.value && !!draft.value, () => { show.value = false }, { closeOnEscape: false })
void dialogRef
</script>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="show && draft" class="modal z-[var(--z-popover)]">
        <div class="modal-backdrop" @click="show = false"></div>
        <div
          ref="dialogRef"
          v-bind="dialogAttrs"
          tabindex="-1"
          class="modal-content modal-surface w-[min(92vw,560px)] max-h-[85vh]"
        >
          <div class="modal-header shrink-0">
            <h3 :id="titleId" class="modal-title">正文正则规则</h3>
            <button type="button" class="modal-close" aria-label="关闭正文正则规则编辑弹窗" @click="show = false">
              <X class="w-5 h-5" />
            </button>
          </div>
          <div class="modal-body drawer-scroll min-h-0 custom-scrollbar">
            <div class="settings-group">
              <SettingsField label="规则名称（可选）">
                <input v-model="draft.name" type="text" class="input w-full" placeholder="留空将使用 pattern 前缀" />
              </SettingsField>
              <SettingsField label="Pattern">
                <textarea
                  v-model="draft.pattern"
                  rows="3"
                  class="input textarea w-full resize-y"
                  placeholder="支持 /pattern/imsu 或普通正则"
                />
              </SettingsField>
              <SettingsField label="动作">
                <ModernSelect
                  v-model="draft.action"
                  :options="[
                    { label: '删除命中内容', value: 'remove' },
                    { label: '替换命中内容', value: 'replace' },
                    { label: '提取到队列', value: 'extract' },
                    { label: '提取并替换显示', value: 'extract_and_replace' },
                  ]"
                />
              </SettingsField>
              <SettingsField
                v-if="draft.action === 'replace' || draft.action === 'extract_and_replace'"
                label="Replacement"
              >
                <textarea
                  v-model="draft.replacement"
                  rows="3"
                  class="input textarea w-full resize-y"
                  placeholder="支持 $1 / $<name>，保存后会归一化"
                />
              </SettingsField>
              <SettingsField
                v-if="draft.action === 'extract' || draft.action === 'extract_and_replace'"
                label="提取来源"
              >
                <ModernSelect
                  v-model="draft.extractSource"
                  :options="[
                    { label: '整段匹配', value: 'whole_match' },
                    { label: '捕获分组', value: 'capture_group' },
                  ]"
                />
              </SettingsField>
              <SettingsField
                v-if="
                  (draft.action === 'extract' || draft.action === 'extract_and_replace') &&
                  draft.extractSource === 'capture_group'
                "
                label="提取分组下标"
              >
                <input
                  v-model.number="draft.extractGroupIndex"
                  type="number"
                  min="0"
                  class="input w-full"
                  placeholder="默认 1"
                />
              </SettingsField>
              <SettingsField label="匹配模式">
                <ModernSelect
                  v-model="draft.matchMode"
                  :options="[
                    { label: '全局命中', value: 'global' },
                    { label: '首个命中', value: 'first' },
                  ]"
                />
              </SettingsField>
              <SettingsField label="覆盖扫描深度（可选）">
                <input
                  v-model.number="draft.scanDepthOverride"
                  type="number"
                  min="1"
                  max="50"
                  class="input w-full"
                  placeholder="留空使用会话默认深度"
                />
              </SettingsField>
            </div>

            <div class="settings-group">
              <div class="settings-field-head">
                <div class="settings-group-title">试运行</div>
                <button type="button" class="btn btn-xs btn-secondary" @click="emit('run-trial')">试运行</button>
              </div>
              <ThemedRadioTags
                v-model="trialSourceMode"
                :options="[...trialSourceOptions]"
                aria-label="试运行来源"
              />
              <textarea
                v-if="trialSourceMode === 'manual'"
                v-model="trialManualText"
                rows="4"
                maxlength="10000"
                class="input textarea w-full resize-y"
                placeholder="输入测试文本（最多 10000 字符）"
              />
              <template v-if="trialResult">
                <SettingsField label="处理前">
                  <pre class="settings-readout whitespace-pre-wrap break-words">{{ trialResult.beforeText }}</pre>
                </SettingsField>
                <SettingsField label="持久化正文（处理后）">
                  <pre class="settings-readout whitespace-pre-wrap break-words">{{ trialResult.afterText }}</pre>
                </SettingsField>
                <SettingsField label="显示正文（处理后）">
                  <pre class="settings-readout whitespace-pre-wrap break-words">{{ trialResult.displayText }}</pre>
                </SettingsField>
                <SettingsField label="提取队列预览">
                  <pre class="settings-readout whitespace-pre-wrap break-words">{{ trialResult.extractedItems.map((x) => x.value).join('\n') || '（空）' }}</pre>
                </SettingsField>
              </template>
            </div>
          </div>
          <div class="modal-footer shrink-0">
            <button type="button" class="btn btn-secondary" @click="show = false">取消</button>
            <button type="button" class="btn btn-primary" @click="emit('save')">保存</button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
