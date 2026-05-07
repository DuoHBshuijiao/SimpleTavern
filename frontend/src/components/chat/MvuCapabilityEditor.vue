<script setup lang="ts">
/**
 * MvuCapabilityEditor - MVU 能力编辑通用面板
 *
 * 抽取自 ChatPage.vue 角色编辑卡片：模式选择 + 指令文本 + 正则规则数组 + 初始状态栏。
 * 不含「启用 MVU」开关——由调用方在外层包一层 `v-if="enabled"`，并自行管理对应字段
 * （角色卡：`mvuEnabled`；群聊：`overrides.groupMvuEnabled`）。
 *
 * 适用场景：
 *  - 角色编辑（allowInherit=false，mvuMode 必为 'regex' | 'directive'）
 *  - 群聊创建弹窗 / 群聊设置弹窗 / 会话设置抽屉（allowInherit=true）
 */
import InitialStateEditor from './InitialStateEditor.vue'
import ModernSelect from '../ModernSelect.vue'
import ThemedCheckbox from '../ThemedCheckbox.vue'
import type { ChatContentRegexRule, ChatMvuMode, StatusTableDef } from '../../types/models'

const props = withDefaults(defineProps<{
  mvuMode: ChatMvuMode
  mvuDirective: string | null
  contentRegexRules: ChatContentRegexRule[]
  initialStateTables: StatusTableDef[]
  /** 是否允许「继承（未指定）」选项；角色卡传 false，会话场景传 true */
  allowInherit?: boolean
  /** 透传给 InitialStateEditor 的副标题（默认空：会话/群场景下隐藏「新会话自动写入」） */
  tablesSubtitle?: string
  /** 透传给 InitialStateEditor 的空状态提示文字 */
  tablesEmptyHint?: string
}>(), {
  allowInherit: false,
  tablesSubtitle: '',
  tablesEmptyHint: '暂无状态表格。点击「新建表格」开始配置。',
})

const emit = defineEmits<{
  (e: 'update:mvuMode', value: ChatMvuMode): void
  (e: 'update:mvuDirective', value: string): void
  (e: 'update:contentRegexRules', value: ChatContentRegexRule[]): void
  (e: 'update:initialStateTables', value: StatusTableDef[]): void
}>()

const modeOptions = [
  ...(props.allowInherit ? [{ label: '继承（未指定）', value: '' }] : []),
  { label: '正则模式', value: 'regex' },
  { label: '指令模式', value: 'directive' },
]

const modeSelectValue = (() => '')

function onModeChange(v: string) {
  if (v === 'regex' || v === 'directive') {
    emit('update:mvuMode', v)
  } else {
    emit('update:mvuMode', null)
  }
}

function onDirectiveInput(e: Event) {
  emit('update:mvuDirective', (e.target as HTMLTextAreaElement).value)
}

function rulesCopy(): ChatContentRegexRule[] {
  return (props.contentRegexRules || []).map((r) => ({ ...r }))
}

function emitRules(rules: ChatContentRegexRule[]) {
  emit('update:contentRegexRules', rules.map((r, i) => ({ ...r, order: i })))
}

function addRule() {
  const next = rulesCopy()
  next.push({
    id: crypto.randomUUID(),
    name: '',
    enabled: true,
    order: next.length,
    pattern: '',
    action: 'remove',
    replacement: '',
    matchMode: 'global',
    extractSource: 'whole_match',
    extractGroupIndex: null,
    scanDepthOverride: null,
  })
  emitRules(next)
}

function removeRule(idx: number) {
  const next = rulesCopy()
  next.splice(idx, 1)
  emitRules(next)
}

function updateRule(idx: number, patch: Partial<ChatContentRegexRule>) {
  const next = rulesCopy()
  if (!next[idx]) return
  next[idx] = { ...next[idx], ...patch }
  emitRules(next)
}

function onTablesUpdate(v: StatusTableDef[]) {
  emit('update:initialStateTables', v)
}

void modeSelectValue
</script>

<template>
  <div class="space-y-3">
    <div class="grid grid-cols-1 md:grid-cols-[minmax(12rem,220px)_1fr] gap-3">
      <div class="space-y-1.5">
        <label class="block text-xs font-medium text-[var(--color-text-secondary)]">MVU 模式</label>
        <ModernSelect
          :model-value="props.mvuMode ?? ''"
          :options="modeOptions"
          placeholder="选择 MVU 模式..."
          @update:model-value="onModeChange"
        />
      </div>
      <div class="text-xs text-[var(--color-text-muted)] self-end pb-2">
        正则模式使用正文正则提取状态变更；指令模式保存给后续 MVU 流程读取的自然语言规则。
      </div>
    </div>

    <div v-if="props.mvuMode === 'directive'" class="space-y-1.5">
      <label class="block text-xs font-medium text-[var(--color-text-secondary)]">MVU 指令</label>
      <textarea
        :value="props.mvuDirective ?? ''"
        class="input textarea h-32"
        placeholder="描述如何从回复中识别状态变化、如何更新状态栏。"
        @input="onDirectiveInput"
      ></textarea>
    </div>

    <template v-else-if="props.mvuMode === 'regex'">
      <div class="flex items-center justify-between">
        <div class="text-xs text-[var(--color-text-muted)]">正文正则规则</div>
        <button type="button" class="btn btn-xs btn-secondary" @click="addRule">新建规则</button>
      </div>
      <div class="space-y-2">
        <div
          v-for="(rule, idx) in props.contentRegexRules || []"
          :key="rule.id || idx"
          class="rounded-lg border border-[var(--color-border-subtle)] bg-surface-muted p-2 space-y-2"
        >
          <div class="flex items-center gap-2">
            <input
              :value="rule.name ?? ''"
              class="input flex-1"
              placeholder="规则名称（可选）"
              @input="updateRule(idx, { name: ($event.target as HTMLInputElement).value })"
            />
            <label class="inline-flex items-center gap-1 text-xs cursor-pointer select-none">
              <ThemedCheckbox
                :checked="rule.enabled"
                @update:checked="(v: boolean) => updateRule(idx, { enabled: v })"
              />
              <span>启用</span>
            </label>
            <button type="button" class="btn btn-xs btn-secondary" @click="removeRule(idx)">删除</button>
          </div>
          <textarea
            :value="rule.pattern"
            class="input textarea h-20"
            placeholder="pattern"
            @input="updateRule(idx, { pattern: ($event.target as HTMLTextAreaElement).value })"
          ></textarea>
          <div class="grid grid-cols-1 md:grid-cols-3 gap-2">
            <ModernSelect
              :model-value="rule.action"
              :options="[
                { label: '删除', value: 'remove' },
                { label: '替换', value: 'replace' },
                { label: '提取', value: 'extract' },
                { label: '提取并替换显示', value: 'extract_and_replace' },
              ]"
              placeholder="选择处理动作..."
              @update:model-value="(v: string) => updateRule(idx, { action: v as ChatContentRegexRule['action'] })"
            />
            <ModernSelect
              :model-value="rule.matchMode ?? 'global'"
              :options="[
                { label: '全局命中', value: 'global' },
                { label: '首个命中', value: 'first' },
              ]"
              placeholder="选择匹配模式..."
              @update:model-value="(v: string) => updateRule(idx, { matchMode: v as ChatContentRegexRule['matchMode'] })"
            />
            <input
              :value="rule.scanDepthOverride ?? ''"
              type="number"
              min="1"
              class="input"
              placeholder="覆盖深度(可选)"
              @input="updateRule(idx, { scanDepthOverride: (() => { const n = Number(($event.target as HTMLInputElement).value); return Number.isFinite(n) && n >= 1 ? n : null })() })"
            />
          </div>
          <textarea
            v-if="rule.action === 'replace' || rule.action === 'extract_and_replace'"
            :value="rule.replacement ?? ''"
            class="input textarea h-16"
            placeholder="replacement"
            @input="updateRule(idx, { replacement: ($event.target as HTMLTextAreaElement).value })"
          ></textarea>
          <div v-if="rule.action === 'extract' || rule.action === 'extract_and_replace'" class="grid grid-cols-1 md:grid-cols-2 gap-2">
            <ModernSelect
              :model-value="rule.extractSource ?? 'whole_match'"
              :options="[
                { label: '整段匹配', value: 'whole_match' },
                { label: '捕获分组', value: 'capture_group' },
              ]"
              placeholder="选择提取来源..."
              @update:model-value="(v: string) => updateRule(idx, { extractSource: v as ChatContentRegexRule['extractSource'] })"
            />
            <input
              v-if="rule.extractSource === 'capture_group'"
              :value="rule.extractGroupIndex ?? ''"
              type="number"
              min="0"
              class="input"
              placeholder="提取分组下标"
              @input="updateRule(idx, { extractGroupIndex: (() => { const n = Number(($event.target as HTMLInputElement).value); return Number.isFinite(n) && n >= 0 ? n : null })() })"
            />
          </div>
        </div>
        <div
          v-if="!(props.contentRegexRules || []).length"
          class="text-xs text-[var(--color-text-muted)] border border-dashed border-[var(--color-border-subtle)] rounded-lg px-3 py-2"
        >
          暂无规则。
        </div>
      </div>
    </template>

    <InitialStateEditor
      :tables="props.initialStateTables || []"
      :subtitle="props.tablesSubtitle"
      :empty-hint="props.tablesEmptyHint"
      @update:tables="onTablesUpdate"
    />
  </div>
</template>
