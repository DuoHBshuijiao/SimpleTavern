<script setup lang="ts">
import { Eye, EyeOff } from 'lucide-vue-next'
import ModernSelect from '../ModernSelect.vue'
import SettingsDrawerGlobalAccordion from './SettingsDrawerGlobalAccordion.vue'
import SettingsField from './SettingsField.vue'
import SettingsSwitch from './SettingsSwitch.vue'
import LlmConnectionAdvancedSection from './LlmConnectionAdvancedSection.vue'
import { llmProtocolSelectOptions } from '../../constants/llmProtocols'
import { REASONING_EFFORT_OPTIONS, REASONING_ECHO_BACK_OPTIONS, type Settings } from '../../types/models'
import type { LlmCatalogProvider } from '../../api/llm'

defineProps<{
  draft: Settings
  mvuModelOptions: Array<{
    label: string
    options: Array<{ label: string; value: string; presetId?: string | null }>
  }>
  catalogProvider?: LlmCatalogProvider | null
}>()

const open = defineModel<boolean>('open', { required: true })
const showApiKeyModel = defineModel<boolean>('showApiKey', { required: true })

const emit = defineEmits<{
  'mvu-model-select': [option: { value: string; presetId?: string | null }]
  'open-cache-guide': []
}>()
</script>

<template>
  <SettingsDrawerGlobalAccordion v-model:open="open" title="连接与默认模型">
    <div class="settings-group">
      <div class="settings-group-title">对话模式</div>
      <SettingsSwitch v-model="draft.streamEnabled" label="流式传输" />
      <SettingsSwitch
        v-model="draft.pureAiMode"
        label="纯 AI 模式"
        more="不注入用户 Persona，用户发言以「系统」角色影响世界。"
      />
    </div>

    <div class="settings-group">
      <div class="settings-group-title">思考</div>
      <SettingsField
        label="思考模式"
        more="选「无」关闭思考，其他档位请求更高的推理深度。聊天面板可以按会话覆盖。"
      >
        <ModernSelect
          v-model="draft.reasoningEffort"
          :options="[...REASONING_EFFORT_OPTIONS]"
          placeholder="选择思考深度..."
          class="w-full"
        />
      </SettingsField>
      <SettingsField
        label="回传思考内容"
        data-settings-field="reasoningEchoBack"
        hint="DeepSeek 带工具调用时必须回传，否则会 400。"
        more="「按预设」看各 API 预设开关；「全部回传 / 不回传」覆盖所有预设。"
      >
        <ModernSelect
          :model-value="draft.reasoningEchoBack || 'preset'"
          :options="[...REASONING_ECHO_BACK_OPTIONS]"
          placeholder="按预设…"
          class="w-full"
          @update:model-value="(v) => { draft.reasoningEchoBack = String(v) as Settings['reasoningEchoBack'] }"
        />
      </SettingsField>
    </div>

    <div class="settings-group">
      <div class="settings-group-title">默认连接</div>
      <SettingsField
        label="API 基础地址"
        more="支持 Base（如 https://api.openai.com 或 …/v1）或完整 chat/completions 地址；末尾有无 / 均可。"
      >
        <input
          v-model="draft.llm.baseUrl"
          type="text"
          placeholder="https://api.openai.com 或 …/v1/chat/completions"
          class="input w-full"
        />
      </SettingsField>
      <SettingsField
        label="LLM 协议"
        more="只在没有匹配到 API 预设时生效。选「自动」会按模型家族切换原生协议，结果在下方预览里能看到。"
      >
        <ModernSelect
          :model-value="draft.llm.protocol || 'openai_compatible_chat'"
          :options="llmProtocolSelectOptions(draft.llm.protocol)"
          placeholder="选择协议…"
          class="w-full"
          @update:model-value="(v) => { draft.llm.protocol = String(v) }"
        />
      </SettingsField>
      <SettingsField label="API Key">
        <div class="relative">
          <input
            v-model="draft.llm.apiKey"
            :type="showApiKeyModel ? 'text' : 'password'"
            class="input w-full pr-11"
          />
          <button
            type="button"
            class="absolute right-1 top-1/2 flex min-h-10 min-w-10 -translate-y-1/2 items-center justify-center rounded-md text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]"
            :aria-label="showApiKeyModel ? '隐藏 API Key' : '显示 API Key'"
            @click="showApiKeyModel = !showApiKeyModel"
          >
            <component :is="showApiKeyModel ? Eye : EyeOff" class="h-4 w-4" />
          </button>
        </div>
      </SettingsField>
      <SettingsField label="模型名称">
        <input
          v-model="draft.llm.defaultModel"
          type="text"
          class="input w-full"
          placeholder="例如: gpt-3.5-turbo"
        />
      </SettingsField>
      <SettingsField
        label="MVU Agent 模型"
        more="MVU 后台和 SillyTavern directive 导入共用这个模型。"
      >
        <ModernSelect
          :model-value="draft.mvuModel ?? ''"
          :options="mvuModelOptions"
          placeholder="留空则使用默认模型名称与候选回退"
          class="w-full"
          searchable
          allow-create
          @select="emit('mvu-model-select', $event)"
        />
      </SettingsField>
    </div>

    <LlmConnectionAdvancedSection
      :connection="draft.llm"
      :models="[draft.llm.defaultModel, ...(draft.llm.usedModels || [])].filter((x): x is string => Boolean(x))"
      :catalog-provider="catalogProvider ?? null"
      :reasoning-effort="draft.reasoningEffort"
      :global-echo-back="draft.reasoningEchoBack ?? 'preset'"
      @open-cache-guide="emit('open-cache-guide')"
    />
  </SettingsDrawerGlobalAccordion>
</template>
