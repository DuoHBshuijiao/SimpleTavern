<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import { SETTINGS_DRAWER_CHAT_KEY } from '../../composables/settingsDrawerChatKey'
import type { ApiPreset } from '../../types/models'
import ModernSelect from '../ModernSelect.vue'
import ThemedCheckbox from '../ThemedCheckbox.vue'
import MvuCapabilityEditor from '../chat/MvuCapabilityEditor.vue'
import SettingsDrawerChatRegexSection from './SettingsDrawerChatRegexSection.vue'
import SettingsDrawerChatWorldBookSection from './SettingsDrawerChatWorldBookSection.vue'
import SettingsDrawerChatTtsSection from './SettingsDrawerChatTtsSection.vue'
import SettingsDrawerGlobalAccordion from './SettingsDrawerGlobalAccordion.vue'
import SettingsField from './SettingsField.vue'
import SettingsHint from './SettingsHint.vue'
import SettingsSwitch from './SettingsSwitch.vue'

const chat = inject(SETTINGS_DRAWER_CHAT_KEY)!

const linkedChatPresetName = computed(() => {
  const presetId = chat.chatDraft?.presetId
  const presets = chat.globalDraft?.apiPresets as ApiPreset[] | undefined
  return presets?.find((p) => p.id === presetId)?.name || '未知预设'
})

const promptOpen = ref(true)
const modelOpen = ref(true)
const mvuOpen = ref(false)
</script>

<template>
  <div>
    <div v-if="!chat.chat" class="settings-hint text-center py-8">请先选择一个会话</div>
    <div v-else-if="chat.chatDraft && chat.globalDraft" class="space-y-4">
      <SettingsHint more="这些设置仅应用于当前会话，并会覆盖全局设置。模型选择将自动关联对应的 API 预设。">
        仅对当前会话生效，会覆盖全局设置。
      </SettingsHint>

      <SettingsDrawerGlobalAccordion v-model:open="promptOpen" title="提示词与记忆">
        <div class="settings-group">
          <SettingsField
            label="会话系统提示"
            hint="追加：接在全局后面；覆盖：非空时跳过全局。"
            more="追加全局会保留全局系统提示并在后面附加本会话内容；覆盖全局会在本会话提示非空时跳过全局系统提示。"
          >
            <template #actions>
              <div class="relative inline-flex shrink-0 gap-1 rounded-lg bg-surface-muted p-1">
                <div
                  class="pointer-events-none absolute left-1 top-1 bottom-1 rounded-md bg-brand shadow-sm transition-transform duration-[var(--motion-duration-moderate)] ease-out"
                  :style="{
                    width: 'calc((100% - 0.75rem) / 2)',
                    transform: `translateX(calc(${chat.chatDraft.sessionSystemPromptMode === 'override' ? 1 : 0} * (100% + 0.25rem)))`,
                  }"
                />
                <button
                  type="button"
                  class="relative z-10 min-w-[4.25rem] flex-1 rounded-md px-2 py-1 text-center text-xs font-medium transition-colors duration-[var(--motion-duration-moderate)] ease-out touch-manipulation"
                  :class="
                    chat.chatDraft.sessionSystemPromptMode === 'append'
                      ? 'text-[var(--color-on-brand)]'
                      : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]'
                  "
                  @click="chat.chatDraft.sessionSystemPromptMode = 'append'"
                >追加全局</button>
                <button
                  type="button"
                  class="relative z-10 min-w-[4.25rem] flex-1 rounded-md px-2 py-1 text-center text-xs font-medium transition-colors duration-[var(--motion-duration-moderate)] ease-out touch-manipulation"
                  :class="
                    chat.chatDraft.sessionSystemPromptMode === 'override'
                      ? 'text-[var(--color-on-brand)]'
                      : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]'
                  "
                  @click="chat.chatDraft.sessionSystemPromptMode = 'override'"
                >覆盖全局</button>
              </div>
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
            hint="静默关闭时，到阈值会先询问。"
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
          <SettingsField label="模型覆盖" :hint="chat.chatDraft?.presetId ? `已关联 API 预设：${linkedChatPresetName}` : undefined">
            <ModernSelect
              v-model="chat.chatDraft.params.model"
              :selected-preset-id="chat.chatDraft?.presetId ?? null"
              :options="chat.chatModelOptions"
              searchable
              allow-create
              placeholder="选择模型 (自动关联预设)..."
              @select="chat.handleChatModelSelect"
            />
          </SettingsField>
          <div class="grid grid-cols-2 gap-4">
            <SettingsField label="Temperature">
              <input
                v-model.number="chat.chatDraft.params.temperature"
                type="number"
                step="0.1" min="0" max="2"
                placeholder="使用全局"
                class="input w-full"
              />
            </SettingsField>
            <SettingsField label="Top P">
              <input
                v-model.number="chat.chatDraft.params.top_p"
                type="number"
                step="0.1" min="0" max="1"
                placeholder="使用全局"
                class="input w-full"
              />
            </SettingsField>
            <SettingsField label="最大输出长度">
              <input
                v-model.number="chat.chatDraft.params.max_tokens"
                type="number"
                step="128" min="1"
                placeholder="使用全局"
                class="input w-full"
              />
            </SettingsField>
          </div>
        </div>
        <div class="settings-group">
          <div class="settings-group-title">上下文</div>
          <div class="grid grid-cols-2 gap-4">
            <SettingsField label="上下文长度">
              <input
                v-model.number="chat.chatDraft.params.context_size"
                type="number"
                min="0"
                placeholder="未启用（使用全局）"
                class="input w-full"
              />
            </SettingsField>
            <SettingsField label="草稿助手条数限制">
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
          <SettingsHint more="实际上下文总限制长度为该「上下文长度」限制加上角色卡、用户信息、自定义系统提示词。草稿助手优先使用当前会话的条数限制，其次全局，最后回退到现有上下文逻辑。">
            角色卡、用户信息和系统提示词不计入上下文长度。
          </SettingsHint>
        </div>
      </SettingsDrawerGlobalAccordion>

      <SettingsDrawerGlobalAccordion v-model:open="mvuOpen" title="MVU 与知识图谱">
        <div v-if="chat.chat?.isGroup" class="settings-group">
          <SettingsSwitch
            :model-value="chat.chatDraft?.groupMvuEnabled === true"
            label="启用群聊 MVU"
            hint="与「群聊设置」弹窗写入同一字段。"
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
          <div class="settings-group-title">MVU 模式覆盖</div>
          <SettingsHint more="只覆盖当前会话的 MVU 模式、指令、正则规则与初始状态栏。MVU 所用模型在全局「连接与默认模型」中配置。">
            只影响当前会话；所用模型在全局设置里配置。
          </SettingsHint>
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
            more="关闭后不注入 RP 上下文，MVU 也不会自动维护图谱；仍可手动打开图谱编辑。"
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
