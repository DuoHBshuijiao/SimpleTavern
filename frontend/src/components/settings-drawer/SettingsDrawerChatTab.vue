<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import { SETTINGS_DRAWER_CHAT_KEY } from '../../composables/settingsDrawerChatKey'
import ModernSelect from '../ModernSelect.vue'
import ThemedCheckbox from '../ThemedCheckbox.vue'
import ThemedRadioTags from '../ThemedRadioTags.vue'
import MvuCapabilityEditor from '../chat/MvuCapabilityEditor.vue'
import SettingsDrawerChatRegexSection from './SettingsDrawerChatRegexSection.vue'
import SettingsDrawerChatWorldBookSection from './SettingsDrawerChatWorldBookSection.vue'
import SettingsDrawerChatTtsSection from './SettingsDrawerChatTtsSection.vue'
import SettingsDrawerGlobalAccordion from './SettingsDrawerGlobalAccordion.vue'
import SettingsField from './SettingsField.vue'
import SettingsHint from './SettingsHint.vue'
import SettingsSwitch from './SettingsSwitch.vue'
import { formatChatGenerationField, resolveChatConnection, type ChatGenerationField } from '../../utils/chatGenerationSettings'

const chat = inject(SETTINGS_DRAWER_CHAT_KEY)!
const promptModeOptions = [
  { value: 'append', label: '追加全局' },
  { value: 'override', label: '覆盖全局' },
]

const savedConnection = computed(() => chat.savedSettings
  ? resolveChatConnection(chat.savedSettings, chat.chat?.overrides)
  : null)
const draftConnection = computed(() => chat.globalDraft
  ? resolveChatConnection(chat.globalDraft, chat.chatDraft)
  : null)
const modelDraftChanged = computed(() => {
  const saved = savedConnection.value
  const draft = draftConnection.value
  if (!draft || !saved) return false
  const stored = chat.chat?.overrides
  return saved.model !== draft.model || saved.presetId !== draft.presetId || saved.connection !== draft.connection
    || saved.issue !== draft.issue || (stored?.params?.model || null) !== (chat.chatDraft?.params?.model || null)
    || (stored?.presetId || null) !== (chat.chatDraft?.presetId || null)
})
const modelScopeHint = computed(() => {
  const scope = chat.chatDraft?.params?.model ? '会话覆盖' : '沿用全局'
  return `${modelDraftChanged.value ? '保存后 · ' : ''}${scope} · ${draftConnection.value?.model || '未设置模型'}`
})

function generationFieldHint(key: ChatGenerationField) {
  const current = formatChatGenerationField(chat.savedSettings?.generationDefaults ?? {}, chat.chat?.overrides?.params, key)
  const draft = formatChatGenerationField(chat.globalDraft?.generationDefaults ?? {}, chat.chatDraft?.params, key)
  return current === draft ? draft : `保存后 · ${draft}`
}

const promptOpen = ref(true)
const modelOpen = ref(true)
const mvuOpen = ref(false)
</script>

<template>
  <div>
    <div v-if="!chat.chat" class="settings-hint text-center py-8">请先选择一个会话</div>
    <div v-else-if="chat.chatDraft && chat.globalDraft" class="space-y-4">
      <section class="space-y-1.5" aria-label="当前会话的模型与连接">
        <h3 class="settings-group-title [overflow-wrap:anywhere]">{{ chat.chat.title || '未命名会话' }}</h3>
        <dl class="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1.5 text-xs">
          <template v-if="savedConnection">
            <dt class="text-[var(--color-text-muted)]">{{ chat.chat.isGroup ? '群聊默认' : '当前使用' }}</dt>
            <dd class="session-current-connection [overflow-wrap:anywhere] text-[var(--color-text-secondary)]">
              {{ savedConnection.model || '未设置模型' }} · {{ savedConnection.connection }}
              <span v-if="savedConnection.issue" class="text-warning"> · {{ savedConnection.issue }}</span>
            </dd>
          </template>
          <template v-if="modelDraftChanged && draftConnection">
            <dt class="text-[var(--color-text-muted)]">保存后</dt>
            <dd class="session-draft-connection [overflow-wrap:anywhere] text-[var(--color-text-secondary)]">
              {{ draftConnection.model || '未设置模型' }} · {{ draftConnection.connection }}
              <span v-if="draftConnection.issue" class="text-warning"> · {{ draftConnection.issue }}</span>
            </dd>
          </template>
        </dl>
      </section>

      <SettingsDrawerGlobalAccordion v-model:open="promptOpen" title="提示词与记忆">
        <div class="settings-group">
          <SettingsField
            label="会话系统提示"
            more="追加全局会保留全局系统提示并在后面附加本会话内容；覆盖全局会在本会话提示非空时跳过全局系统提示。"
          >
            <template #actions>
              <ThemedRadioTags
                v-model="chat.chatDraft.sessionSystemPromptMode"
                :options="promptModeOptions"
                aria-label="会话系统提示模式"
                class="shrink-0"
              />
            </template>
            <textarea
              v-model="chat.chatDraft.prompt"
              rows="4"
              placeholder="留空则使用角色默认提示词"
              class="input textarea w-full resize-y"
            ></textarea>
          </SettingsField>
        </div>

        <div class="settings-group">
          <div class="settings-group-title">长期记忆</div>
          <div class="settings-readout flex flex-wrap gap-x-4 gap-y-0.5">
            <span>记忆长度估算：{{ chat.memoryTokenDisplay }} tokens</span>
            <span>对话长度估算：{{ chat.chatTokenDisplay }} tokens</span>
            <span v-if="chat.messagesSinceLastMemoryUpdate != null && chat.tokensSinceLastMemoryUpdate != null">
              距上次保存记忆：~{{ chat.messagesSinceLastMemoryUpdate }} 条消息，约 {{ chat.tokensSinceLastMemoryUpdate }} tokens
            </span>
          </div>
          <div class="memory-cutoff-row flex flex-wrap items-center gap-2">
            <button class="btn btn-xs btn-secondary" @click="chat.hideSavedFloors">从已存记忆处截断</button>
            <button class="btn btn-xs btn-secondary" @click="chat.resetHiddenFloors">恢复完整上下文</button>
            <div
              class="memory-keep-control settings-hint flex items-center gap-1"
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
            <span v-if="chat.chatDraft.contextStartMessageId" class="memory-anchor-hint settings-hint order-2">
              当前已设置上下文起点
            </span>
          </div>
          <textarea
            v-model="chat.chatDraft.longTermMemory"
            rows="4"
            placeholder="会插入系统提示词，留空则不启用"
            class="input textarea w-full resize-y"
          ></textarea>
          <SettingsField
            label="每隔几条消息自动总结"
            more="关闭「静默总结」时，达到阈值会先询问；若拒绝则下次在 n×2、n×3… 条时再问。达到条件时若主聊仍在生成回复，会等生成结束后再判断。"
          >
            <template #actions>
              <label class="settings-hint flex shrink-0 cursor-pointer select-none items-center gap-2">
                <ThemedCheckbox
                  :checked="chat.chatDraft.autoMemorySummarySilent === true"
                  @update:checked="chat.setAutoMemorySummarySilent"
                />
                <span>静默总结</span>
              </label>
            </template>
            <input
              :value="chat.chatDraft.autoMemorySummaryEveryN ?? ''"
              type="number"
              min="1"
              step="1"
              placeholder="关闭"
              class="input w-full"
              @input="chat.onAutoMemorySummaryEveryNInput"
            />
          </SettingsField>
        </div>
      </SettingsDrawerGlobalAccordion>

      <SettingsDrawerGlobalAccordion v-model:open="modelOpen" title="模型与生成参数">
        <div class="settings-group">
          <SettingsField label="模型覆盖" :hint="modelScopeHint">
            <template #actions>
              <button
                v-if="chat.chatDraft.params.model || chat.chatDraft.presetId"
                type="button"
                class="btn btn-xs btn-link"
                @click="chat.handleChatModelSelect({ value: '' })"
              >
                恢复沿用全局
              </button>
            </template>
            <ModernSelect
              :model-value="chat.chatDraft.params.model"
              :selected-preset-id="draftConnection?.presetId ?? null"
              :options="chat.chatModelOptions"
              searchable
              allow-create
              aria-label="模型覆盖"
              placeholder="选择模型..."
              @select="chat.handleChatModelSelect"
            />
          </SettingsField>
          <div class="grid grid-cols-2 gap-4">
            <SettingsField label="Temperature" :hint="generationFieldHint('temperature')">
              <input
                v-model.number="chat.chatDraft.params.temperature"
                type="number"
                step="0.1" min="0" max="2"
                aria-label="Temperature"
                class="input w-full"
              />
            </SettingsField>
            <SettingsField label="Top P" :hint="generationFieldHint('top_p')">
              <input
                v-model.number="chat.chatDraft.params.top_p"
                type="number"
                step="0.1" min="0" max="1"
                aria-label="Top P"
                class="input w-full"
              />
            </SettingsField>
            <SettingsField label="最大输出长度" :hint="generationFieldHint('max_tokens')">
              <input
                v-model.number="chat.chatDraft.params.max_tokens"
                type="number"
                step="128" min="1"
                aria-label="最大输出长度"
                class="input w-full"
              />
            </SettingsField>
          </div>
        </div>
        <div class="settings-group">
          <div class="settings-group-title">上下文</div>
          <div class="grid grid-cols-2 gap-4">
            <SettingsField label="上下文长度" :hint="generationFieldHint('context_size')" more="留空沿用全局，填 0 关闭此会话的上下文长度限制。角色卡、用户信息和系统提示词不计入这个长度。">
              <input
                v-model.number="chat.chatDraft.params.context_size"
                type="number"
                min="0" step="1"
                aria-label="上下文长度"
                class="input w-full"
              />
            </SettingsField>
            <SettingsField label="草稿助手条数限制" more="优先用当前会话的限制，其次用全局的；都留空就按上下文长度处理。">
              <input
                :value="chat.chatDraft.draftHelp?.context_message_limit ?? ''"
                type="text"
                inputmode="numeric"
                pattern="[0-9]*"
                placeholder="使用全局；留空则继续回退"
                class="input w-full"
                @input="chat.handleChatDraftHelpLimitInput"
              />
            </SettingsField>
          </div>
        </div>
      </SettingsDrawerGlobalAccordion>

      <SettingsDrawerGlobalAccordion v-model:open="mvuOpen" title="MVU 与知识图谱">
        <div v-if="chat.chat?.isGroup" class="settings-group">
          <SettingsSwitch
            :model-value="chat.chatDraft?.groupMvuEnabled === true"
            label="启用群聊 MVU"
            @update:model-value="(v) => { if (chat.chatDraft) chat.chatDraft.groupMvuEnabled = v }"
          />
          <template v-if="chat.chatDraft?.groupMvuEnabled === true">
            <SettingsField label="锚定成员">
              <ModernSelect
                :model-value="chat.chatDraft?.groupMvuAnchorCharacterId || ''"
                :options="chat.groupChatMvuAnchorSelectOptions"
                placeholder="选择成员"
                class="w-full"
                @update:model-value="(v) => { if (chat.chatDraft) chat.chatDraft.groupMvuAnchorCharacterId = v || null }"
              />
            </SettingsField>
            <SettingsField label="模板成员（可选）">
              <ModernSelect
                :model-value="chat.chatDraft?.groupMvuTemplateCharacterId || ''"
                :options="chat.groupChatMvuAnchorSelectOptions"
                placeholder="可选"
                class="w-full"
                @update:model-value="(v) => { if (chat.chatDraft) chat.chatDraft.groupMvuTemplateCharacterId = v || null }"
              />
            </SettingsField>
          </template>
        </div>

        <div class="settings-group">
          <SettingsHint title="MVU 模式覆盖" more="只覆盖当前会话的 MVU 模式、指令、正则规则和初始状态栏。MVU 所用模型在全局「连接与默认模型」里配置。" />
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

        <div v-if="chat.chatMvuRuntimeEnabled" class="settings-group">
          <div class="settings-group-title">知识图谱</div>
          <SettingsSwitch
            :model-value="chat.chatDraft?.knowledgeGraphEnabled !== false"
            label="启用知识图谱"
            :hint="chat.kgStatsSummary"
            more="开启后，聊天会参考图谱，MVU 会随剧情更新图谱。"
            @update:model-value="(v) => { if (chat.chatDraft) chat.chatDraft.knowledgeGraphEnabled = v }"
          />
          <div class="flex flex-wrap gap-2">
            <button type="button" class="btn btn-sm btn-secondary" @click="chat.openKnowledgeGraph()">
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
      </SettingsDrawerGlobalAccordion>

      <SettingsDrawerChatRegexSection />
      <SettingsDrawerChatWorldBookSection />
      <SettingsDrawerChatTtsSection />
    </div>
  </div>
</template>
