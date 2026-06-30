<script setup lang="ts">
import { X } from 'lucide-vue-next'
import ModernSelect from '../ModernSelect.vue'
import ThemedRadioTags from '../ThemedRadioTags.vue'
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
</script>

<template>
  <Teleport to="body">
    <div v-if="show && draft" class="fixed inset-0 z-[var(--z-popover)] flex items-center justify-center">
      <div class="modal-backdrop" @click="show = false" />
      <div
        class="glass-l5 relative m-4 flex max-h-[85vh] w-[min(92vw,560px)] flex-col rounded-2xl border border-[var(--color-border)] shadow-xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="regex-editor-title"
      >
        <div class="flex items-center justify-between rounded-t-2xl border-b border-[var(--color-border)] bg-surface-muted p-4">
          <h3 id="regex-editor-title" class="text-[var(--color-text)]">正文正则规则</h3>
          <button
            type="button"
            class="icon-button min-h-11 min-w-11"
            aria-label="关闭正文正则规则编辑弹窗"
            @click="show = false"
          >
            <X class="w-5 h-5" />
          </button>
        </div>
        <div class="drawer-scroll min-h-0 flex-1 overflow-y-auto space-y-3 p-4">
          <div class="space-y-1.5">
            <label class="block text-xs font-medium text-[var(--color-text-secondary)]">规则名称（可选）</label>
            <input v-model="draft.name" type="text" class="input w-full" placeholder="留空将使用 pattern 前缀" />
          </div>
          <div class="space-y-1.5">
            <label class="block text-xs font-medium text-[var(--color-text-secondary)]">Pattern</label>
            <textarea
              v-model="draft.pattern"
              rows="3"
              class="input textarea w-full resize-y"
              placeholder="支持 /pattern/imsu 或普通正则"
            />
          </div>
          <div class="grid grid-cols-1 gap-3">
            <div class="space-y-1.5">
              <label class="block text-xs font-medium text-[var(--color-text-secondary)]">动作</label>
              <ModernSelect
                v-model="draft.action"
                :options="[
                  { label: '删除命中内容', value: 'remove' },
                  { label: '替换命中内容', value: 'replace' },
                  { label: '提取到队列', value: 'extract' },
                  { label: '提取并替换显示', value: 'extract_and_replace' },
                ]"
              />
            </div>
            <div
              v-if="draft.action === 'replace' || draft.action === 'extract_and_replace'"
              class="space-y-1.5"
            >
              <label class="block text-xs font-medium text-[var(--color-text-secondary)]">Replacement</label>
              <textarea
                v-model="draft.replacement"
                rows="3"
                class="input textarea w-full resize-y"
                placeholder="支持 $1 / $<name>，保存后会归一化"
              />
            </div>
            <div
              v-if="draft.action === 'extract' || draft.action === 'extract_and_replace'"
              class="space-y-1.5"
            >
              <label class="block text-xs font-medium text-[var(--color-text-secondary)]">提取来源</label>
              <ModernSelect
                v-model="draft.extractSource"
                :options="[
                  { label: '整段匹配', value: 'whole_match' },
                  { label: '捕获分组', value: 'capture_group' },
                ]"
              />
            </div>
            <div
              v-if="
                (draft.action === 'extract' || draft.action === 'extract_and_replace') &&
                draft.extractSource === 'capture_group'
              "
              class="space-y-1.5"
            >
              <label class="block text-xs font-medium text-[var(--color-text-secondary)]">提取分组下标</label>
              <input
                v-model.number="draft.extractGroupIndex"
                type="number"
                min="0"
                class="input w-full"
                placeholder="默认 1"
              />
            </div>
            <div class="space-y-1.5">
              <label class="block text-xs font-medium text-[var(--color-text-secondary)]">匹配模式</label>
              <ModernSelect
                v-model="draft.matchMode"
                :options="[
                  { label: '全局命中', value: 'global' },
                  { label: '首个命中', value: 'first' },
                ]"
              />
            </div>
            <div class="space-y-1.5">
              <label class="block text-xs font-medium text-[var(--color-text-secondary)]">覆盖扫描深度（可选）</label>
              <input
                v-model.number="draft.scanDepthOverride"
                type="number"
                min="1"
                max="50"
                class="input w-full"
                placeholder="留空使用会话默认深度"
              />
            </div>
          </div>

          <div class="space-y-2 rounded-lg border border-[var(--color-border-subtle)] bg-surface-muted p-3">
            <div class="text-xs font-medium text-[var(--color-text-secondary)]">试运行</div>
            <div>
              <ThemedRadioTags
                v-model="trialSourceMode"
                :options="[...trialSourceOptions]"
                aria-label="试运行来源"
              />
            </div>
            <textarea
              v-if="trialSourceMode === 'manual'"
              v-model="trialManualText"
              rows="4"
              maxlength="10000"
              class="input textarea w-full resize-y"
              placeholder="输入测试文本（最多 10000 字符）"
            />
            <button type="button" class="btn btn-xs btn-secondary" @click="emit('run-trial')">试运行</button>
            <div v-if="trialResult" class="grid grid-cols-1 gap-2 text-xs">
              <div>
                <div class="mb-1 text-[var(--color-text-secondary)]">处理前</div>
                <pre class="whitespace-pre-wrap rounded border border-[var(--color-border-subtle)] bg-surface-overlay p-2">{{ trialResult.beforeText }}</pre>
              </div>
              <div>
                <div class="mb-1 text-[var(--color-text-secondary)]">持久化正文（处理后）</div>
                <pre class="whitespace-pre-wrap rounded border border-[var(--color-border-subtle)] bg-surface-overlay p-2">{{ trialResult.afterText }}</pre>
              </div>
              <div>
                <div class="mb-1 text-[var(--color-text-secondary)]">显示正文（处理后）</div>
                <pre class="whitespace-pre-wrap rounded border border-[var(--color-border-subtle)] bg-surface-overlay p-2">{{ trialResult.displayText }}</pre>
              </div>
              <div>
                <div class="mb-1 text-[var(--color-text-secondary)]">提取队列预览</div>
                <pre class="whitespace-pre-wrap rounded border border-[var(--color-border-subtle)] bg-surface-overlay p-2">{{ trialResult.extractedItems.map((x) => x.value).join('\n') || '（空）' }}</pre>
              </div>
            </div>
          </div>
        </div>
        <div class="flex items-center justify-end gap-2 rounded-b-2xl border-t border-[var(--color-border)] bg-surface-muted p-4">
          <button type="button" class="btn btn-secondary" @click="show = false">取消</button>
          <button type="button" class="btn btn-primary" @click="emit('save')">保存</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
