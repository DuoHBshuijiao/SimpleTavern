<script setup lang="ts">
import { computed, inject } from 'vue'
import { SETTINGS_DRAWER_CHAT_KEY } from '../../composables/settingsDrawerChatKey'
import type { ApiPreset } from '../../types/models'
import ModernSelect from '../ModernSelect.vue'
import ThemedCheckbox from '../ThemedCheckbox.vue'
import MvuCapabilityEditor from '../chat/MvuCapabilityEditor.vue'
import SettingsDrawerChatRegexSection from './SettingsDrawerChatRegexSection.vue'
import SettingsDrawerChatWorldBookSection from './SettingsDrawerChatWorldBookSection.vue'
import SettingsDrawerChatTtsSection from './SettingsDrawerChatTtsSection.vue'

const chat = inject(SETTINGS_DRAWER_CHAT_KEY)!

const linkedChatPresetName = computed(() => {
  const presetId = chat.chatDraft?.presetId
  const presets = chat.globalDraft?.apiPresets as ApiPreset[] | undefined
  return presets?.find((p) => p.id === presetId)?.name || '未知预设'
})
</script>

<template>
  <div>
    <div v-if="!chat.chat" class="text-center text-[var(--color-text-muted)] py-8">请先选择一个会话</div>
    <div v-else-if="chat.chatDraft && chat.globalDraft" class="space-y-5">
 <div class="text-xs text-[var(--color-text-muted)] bg-surface-muted p-3 rounded-lg border border-[var(--color-border-subtle)]">
  这些设置仅应用于当前会话，并会覆盖全局设置。模型选择将自动关联对应的 API 预设。
</div>

<div class="space-y-2">
  <div class="flex items-center justify-between gap-3">
    <label class="block text-sm font-medium text-[var(--color-text-secondary)]">会话系统提示</label>
    <div class="relative inline-flex shrink-0 gap-1 rounded-lg border border-[var(--color-border-subtle)] bg-surface-muted p-1">
      <div
        class="pointer-events-none absolute left-1 top-1 bottom-1 rounded-md bg-brand shadow-sm transition-transform duration-[400ms] ease-out"
        :style="{
          width: 'calc((100% - 0.75rem) / 2)',
          transform: `translateX(calc(${chat.chatDraft.sessionSystemPromptMode === 'override' ? 1 : 0} * (100% + 0.25rem)))`,
        }"
      />
      <button
        type="button"
        class="relative z-10 min-w-[4.25rem] flex-1 rounded-md px-2 py-1 text-center text-xs font-medium transition-colors duration-[400ms] ease-out touch-manipulation"
        :class="
          chat.chatDraft.sessionSystemPromptMode === 'append'
            ? 'text-[var(--color-on-brand)]'
            : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]'
        "
        @click="chat.chatDraft.sessionSystemPromptMode = 'append'"
      >追加全局</button>
      <button
        type="button"
        class="relative z-10 min-w-[4.25rem] flex-1 rounded-md px-2 py-1 text-center text-xs font-medium transition-colors duration-[400ms] ease-out touch-manipulation"
        :class="
          chat.chatDraft.sessionSystemPromptMode === 'override'
            ? 'text-[var(--color-on-brand)]'
            : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]'
        "
        @click="chat.chatDraft.sessionSystemPromptMode = 'override'"
      >覆盖全局</button>
    </div>
  </div>
  <p class="text-xs text-[var(--color-text-muted)]">
    追加全局会保留全局系统提示并在后面附加本会话内容；覆盖全局会在本会话提示非空时跳过全局系统提示。
  </p>
  <textarea 
    v-model="chat.chatDraft.prompt" 
    rows="4"
    placeholder="留空则使用角色默认提示词"
    class="input textarea w-full resize-y"
  ></textarea>
</div>

<div class="space-y-1.5">
  <div class="flex items-center justify-between gap-4">
    <label class="block text-sm font-medium text-[var(--color-text-secondary)]">长期记忆</label>
    <div class="text-right text-xs text-[var(--color-text-secondary)] shrink-0">
      <div>记忆长度估算：{{ chat.memoryTokenDisplay }} tokens</div>
      <div>对话长度估算：{{ chat.chatTokenDisplay }} tokens</div>
      <div
        v-if="chat.messagesSinceLastMemoryUpdate != null && chat.tokensSinceLastMemoryUpdate != null"
        class="text-[var(--color-text-muted)]"
      >
        距离上次保存记忆已过去了：
        <br v-if="chat.isNarrowPortrait" />
        ~{{ chat.messagesSinceLastMemoryUpdate }} 条消息，约 {{ chat.tokensSinceLastMemoryUpdate }} tokens
      </div>
    </div>
  </div>
  <div class="memory-cutoff-row flex flex-wrap items-center gap-2 pb-1">
    <button class="btn btn-xs btn-secondary" @click="chat.hideSavedFloors">从已存记忆处截断</button>
    <button class="btn btn-xs btn-secondary" @click="chat.resetHiddenFloors">恢复完整上下文</button>
    <div
      class="memory-keep-control flex items-center gap-1 text-xs text-[var(--color-text-secondary)]"
      :class="chat.isNarrowPortrait ? 'basis-full justify-start order-3' : 'ml-auto justify-end order-3'"
    >
      <span>向前保留</span>
      <input
        :value="chat.chatDraft.contextStartKeepBeforeMessages ?? ''"
        type="number"
        min="2"
        step="1"
        placeholder="N"
        class="input h-7 w-20 px-2 text-xs"
        @input="chat.onContextStartKeepBeforeMessagesInput"
      />
      <span>条</span>
    </div>
    <span v-if="chat.chatDraft.contextStartMessageId" class="memory-anchor-hint order-2 text-xs text-[var(--color-text-muted)]">
      当前已设置上下文起点
    </span>
  </div>
  <textarea 
    v-model="chat.chatDraft.longTermMemory"
    rows="4"
    placeholder="会插入系统提示词，留空则不启用"
    class="input textarea w-full resize-y"
  ></textarea>
  <div class="flex flex-wrap items-end gap-3 pt-1">
    <div class="space-y-1 min-w-[12rem] flex-1">
      <label class="block text-xs font-medium text-[var(--color-text-secondary)]">每隔几条消息自动总结</label>
      <input
        :value="chat.chatDraft.autoMemorySummaryEveryN ?? ''"
        type="number"
        min="1"
        step="1"
        placeholder="关闭"
        class="input w-full"
        @input="chat.onAutoMemorySummaryEveryNInput"
      />
    </div>
    <label class="flex items-center gap-2 cursor-pointer select-none pb-1.5 shrink-0">
      <ThemedCheckbox
        :checked="chat.chatDraft.autoMemorySummarySilent === true"
        @update:checked="chat.setAutoMemorySummarySilent"
      />
      <span class="text-sm text-[var(--color-text-secondary)]">静默总结</span>
    </label>
  </div>
  <p class="text-xs text-[var(--color-text-muted)]">
    关闭「静默总结」时，达到阈值会先询问；若拒绝则下次在 n×2、n×3… 条时再问。达到条件时若主聊仍在生成回复，会等生成结束后再判断。
  </p>
</div>

 <div class="space-y-1.5">
  <label class="block text-sm font-medium text-[var(--color-text-secondary)]">模型覆盖</label>
  <ModernSelect
    v-model="chat.chatDraft.params.model"
    :selected-preset-id="chat.chatDraft?.presetId ?? null"
    :options="chat.chatModelOptions"
    searchable
    allow-create
    placeholder="选择模型 (自动关联预设)..."
    @select="chat.handleChatModelSelect"
  />
  <div v-if="chat.chatDraft?.presetId" class="text-xs text-brand mt-1 flex items-center gap-1">
      <span>🔗 已关联 API 预设:</span>
      <span>{{ linkedChatPresetName }}</span>
  </div>
</div>

 <div class="grid grid-cols-2 gap-4">
  <div class="space-y-1.5">
    <label class="block text-sm font-medium text-[var(--color-text-secondary)]">Temperature</label>
    <input 
      v-model.number="chat.chatDraft.params.temperature" 
      type="number" 
      step="0.1" min="0" max="2"
      placeholder="使用全局"
      class="input w-full"
    />
  </div>
  <div class="space-y-1.5">
    <label class="block text-sm font-medium text-[var(--color-text-secondary)]">Top P</label>
    <input 
      v-model.number="chat.chatDraft.params.top_p" 
      type="number" 
      step="0.1" min="0" max="1"
      placeholder="使用全局"
      class="input w-full"
    />
  </div>
  <div class="space-y-1.5">
    <label class="block text-sm font-medium text-[var(--color-text-secondary)]">最大输出长度</label>
    <input 
      v-model.number="chat.chatDraft.params.max_tokens" 
      type="number" 
      step="128" min="1"
      placeholder="使用全局"
      class="input w-full"
    />
  </div>
</div>
<div class="space-y-2">
  <div class="text-sm font-medium text-[var(--color-text-secondary)]">上下文</div>
  <div class="grid grid-cols-2 gap-4">
  <div class="space-y-1.5">
    <label class="block text-sm font-medium text-[var(--color-text-secondary)]">上下文长度</label>
    <input 
      v-model.number="chat.chatDraft.params.context_size" 
      type="number" 
      min="0"
      placeholder="未启用（使用全局）"
      class="input w-full"
    />
  </div>
    <div class="space-y-1.5">
      <label class="block text-sm font-medium text-[var(--color-text-secondary)]">草稿助手上下文条数限制</label>
      <input
        :value="chat.chatDraft.draftHelp?.context_message_limit ?? ''"
        type="text"
        inputmode="numeric"
        pattern="[0-9]*"
        placeholder="使用全局；留空则继续回退"
        class="input w-full"
        @input="chat.handleChatDraftHelpLimitInput"
      />
    </div>
  </div>
</div>
<p class="text-xs text-[var(--color-text-muted)] mt-2">实际上下文总限制长度为该「上下文长度」限制加上角色卡、用户信息、自定义系统提示词。草稿助手优先使用当前会话的条数限制，其次全局，最后回退到现有上下文逻辑。</p>

<div v-if="chat.chatDraft && chat.chat?.isGroup" class="space-y-3 rounded-lg border border-[var(--color-border-subtle)] bg-surface-overlay p-3">
  <div class="text-sm font-medium text-[var(--color-text-secondary)]">群聊 MVU</div>
  <label class="inline-flex items-center gap-2 text-sm text-[var(--color-text-secondary)] cursor-pointer select-none">
    <ThemedCheckbox
      :checked="chat.chatDraft?.groupMvuEnabled === true"
      @update:checked="(v) => { if (chat.chatDraft) chat.chatDraft.groupMvuEnabled = v }"
    />
    <span>启用群聊 MVU</span>
  </label>
  <div v-if="chat.chatDraft?.groupMvuEnabled === true" class="w-full min-w-0 space-y-3">
    <div class="block w-full min-w-[12rem] max-w-md space-y-1.5">
      <label class="block w-full min-w-0 text-xs font-medium text-[var(--color-text-secondary)]">锚定成员</label>
      <ModernSelect
        :model-value="chat.chatDraft?.groupMvuAnchorCharacterId || ''"
        @update:model-value="(v) => { if (chat.chatDraft) chat.chatDraft.groupMvuAnchorCharacterId = v || null }"
        :options="chat.groupChatMvuAnchorSelectOptions"
        placeholder="选择成员"
        class="w-full"
      />
    </div>
    <div class="block w-full min-w-[12rem] max-w-md space-y-1.5">
      <label class="block w-full min-w-0 text-xs font-medium text-[var(--color-text-secondary)]">模板成员（可选）</label>
      <ModernSelect
        :model-value="chat.chatDraft?.groupMvuTemplateCharacterId || ''"
        @update:model-value="(v) => { if (chat.chatDraft) chat.chatDraft.groupMvuTemplateCharacterId = v || null }"
        :options="chat.groupChatMvuAnchorSelectOptions"
        placeholder="可选"
        class="w-full"
      />
    </div>
    <p class="text-xs text-[var(--color-text-muted)]">与「群聊设置」弹窗写入同一字段。</p>
  </div>
</div>

<div class="space-y-3 rounded-lg border border-[var(--color-border-subtle)] bg-surface-overlay p-3">
  <div>
    <div class="text-sm font-medium text-[var(--color-text-secondary)]">MVU 模式覆盖</div>
    <div class="mt-1 text-xs text-[var(--color-text-muted)]">只覆盖当前会话的 MVU 模式、指令、正则规则与初始状态栏。MVU 所用模型在全局「连接与默认模型」中配置。</div>
  </div>
  <MvuCapabilityEditor
    :mvu-mode="chat.chatDraft.mvuMode ?? null"
    :mvu-directive="chat.chatDraft.mvuDirective ?? ''"
    :content-regex-rules="chat.chatDraft.contentRegexRules || []"
    :initial-state-tables="chat.chatStateTablesDraft"
    :allow-inherit="true"
    tables-empty-hint="暂无状态表格。点击「新建表格」开始配置。"
    @update:mvu-mode="(v) => { if (chat.chatDraft) chat.chatDraft.mvuMode = v }"
    @update:mvu-directive="(v) => { if (chat.chatDraft) chat.chatDraft.mvuDirective = v }"
    @update:content-regex-rules="(v) => { if (chat.chatDraft) chat.chatDraft.contentRegexRules = v }"
    @update:initial-state-tables="chat.setChatStateTablesDraft"
  />
</div>

<div
  v-if="chat.chatMvuRuntimeEnabled"
  class="space-y-3 rounded-lg border border-[var(--color-border-subtle)] bg-surface-overlay p-3"
>
  <div>
    <div class="text-sm font-medium text-[var(--color-text-secondary)]">知识图谱</div>
    <p class="mt-1 text-xs text-[var(--color-text-muted)]">{{ chat.kgStatsSummary }}</p>
  </div>
  <label class="inline-flex items-center gap-2 text-sm text-[var(--color-text-secondary)] cursor-pointer select-none">
    <ThemedCheckbox
      :checked="chat.chatDraft?.knowledgeGraphEnabled !== false"
      @update:checked="(v) => { if (chat.chatDraft) chat.chatDraft.knowledgeGraphEnabled = v }"
    />
    <span>启用知识图谱</span>
  </label>
  <p class="text-xs text-[var(--color-text-muted)]">
    关闭后不注入 RP 上下文，MVU 也不会自动维护图谱；仍可手动打开图谱编辑。
  </p>
  <div class="flex flex-wrap gap-2">
    <button type="button" class="btn btn-sm btn-primary" @click="chat.openKnowledgeGraph()">
      打开图谱
    </button>
    <button
      v-if="chat.mvuStore.hasKnowledgeGraph"
      type="button"
      class="btn btn-sm btn-secondary"
      @click="chat.clearKnowledgeGraph"
    >
      清空图谱
    </button>
  </div>
</div>


    <SettingsDrawerChatRegexSection />
    <SettingsDrawerChatWorldBookSection />
    <SettingsDrawerChatTtsSection />
    </div>
  </div>
</template>
