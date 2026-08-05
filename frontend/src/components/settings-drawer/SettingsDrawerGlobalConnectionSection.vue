<script setup lang="ts">
import { Eye, EyeOff } from 'lucide-vue-next'
import ModernSelect from '../ModernSelect.vue'
import SettingsDrawerGlobalAccordion from './SettingsDrawerGlobalAccordion.vue'
import { llmProtocolSelectOptions } from '../../constants/llmProtocols'
import { REASONING_EFFORT_OPTIONS, type Settings } from '../../types/models'

defineProps<{
  draft: Settings
  mvuModelOptions: Array<{
    label: string
    options: Array<{ label: string; value: string; presetId?: string | null }>
  }>
}>()

const open = defineModel<boolean>('open', { required: true })
const showApiKeyModel = defineModel<boolean>('showApiKey', { required: true })

const emit = defineEmits<{
  'mvu-model-select': [option: { value: string; presetId?: string | null }]
}>()
</script>

<template>
  <SettingsDrawerGlobalAccordion v-model:open="open" title="连接与默认模型" content-class="space-y-5">
    <div class="space-y-2">
      <label class="block text-sm font-medium text-[var(--color-text-secondary)]">流式传输</label>
      <button
        type="button"
        class="group flex min-h-11 w-full cursor-pointer items-center gap-3 py-1 text-left"
        @click="draft.streamEnabled = !draft.streamEnabled"
      >
        <div
          class="relative h-6 w-11 shrink-0 rounded-full transition-colors duration-200 ease-out"
          :class="draft.streamEnabled ? 'bg-brand' : 'bg-[var(--color-track)]'"
        >
          <div
            class="absolute left-1 top-1 h-4 w-4 rounded-full bg-[var(--color-on-brand)]"
            :style="{
              transform: draft.streamEnabled ? 'translateX(1.25rem)' : 'translateX(0)',
              transition: 'transform 200ms ease-out',
            }"
          />
        </div>
        <span class="text-xs text-[var(--color-text-secondary)]">
          {{ draft.streamEnabled ? '已开启' : '已关闭' }}
        </span>
      </button>
    </div>

    <div class="space-y-2">
      <label class="block text-sm font-medium text-[var(--color-text-secondary)]">纯 AI 模式</label>
      <button
        type="button"
        class="group flex min-h-11 w-full cursor-pointer items-center gap-3 py-1 text-left"
        @click="draft.pureAiMode = !draft.pureAiMode"
      >
        <div
          class="relative h-6 w-11 shrink-0 rounded-full transition-colors duration-200 ease-out"
          :class="draft.pureAiMode ? 'bg-brand' : 'bg-[var(--color-track)]'"
        >
          <div
            class="absolute left-1 top-1 h-4 w-4 rounded-full bg-[var(--color-on-brand)]"
            :style="{
              transform: draft.pureAiMode ? 'translateX(1.25rem)' : 'translateX(0)',
              transition: 'transform 200ms ease-out',
            }"
          />
        </div>
        <span class="text-xs text-[var(--color-text-secondary)]">
          {{
            draft.pureAiMode
              ? '已开启：不注入用户 Persona，用户发言将以「系统」角色影响世界'
              : '已关闭：正常对话模式'
          }}
        </span>
      </button>
    </div>

    <div class="space-y-1.5">
      <label class="block text-sm font-medium text-[var(--color-text-secondary)]">思考模式</label>
      <ModernSelect
        v-model="draft.reasoningEffort"
        :options="[...REASONING_EFFORT_OPTIONS]"
        placeholder="选择思考深度..."
        class="w-full"
      />
      <p class="text-xs text-[var(--color-text-muted)]">选「无」则关闭思考；其他档位会开启思考并请求更高推理深度。</p>
    </div>

    <div class="space-y-1.5">
      <label class="block text-sm font-medium text-[var(--color-text-secondary)]">默认 API 基础地址</label>
      <input
        v-model="draft.llm.baseUrl"
        type="text"
        placeholder="https://api.openai.com 或 …/v1/chat/completions"
        class="input w-full"
      />
      <p class="text-xs text-[var(--color-text-muted)]">
        支持 Base（如 https://api.openai.com 或 …/v1）或完整 chat/completions 地址；末尾有无 / 均可。
      </p>
    </div>

    <div class="space-y-1.5">
      <label class="block text-sm font-medium text-[var(--color-text-secondary)]">默认 LLM 协议</label>
      <ModernSelect
        :model-value="draft.llm.protocol || 'openai_compatible_chat'"
        :options="llmProtocolSelectOptions(draft.llm.protocol)"
        placeholder="选择协议…"
        class="w-full"
        @update:model-value="(v) => { draft.llm.protocol = String(v) }"
      />
      <p class="text-xs text-[var(--color-text-muted)]">
        仅在使用全局凭证（未匹配到 API 预设）时生效；未知/未实现协议会明确失败。
      </p>
    </div>

    <div class="space-y-1.5">
      <label class="block text-sm font-medium text-[var(--color-text-secondary)]">默认 API Key</label>
      <div class="relative">
        <input
          v-model="draft.llm.apiKey"
          :type="showApiKeyModel ? 'text' : 'password'"
          class="input w-full pr-11"
        />
        <button
          type="button"
          class="absolute right-1 top-1/2 flex min-h-10 min-w-10 -translate-y-1/2 items-center justify-center rounded-md text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]"
          @click="showApiKeyModel = !showApiKeyModel"
        >
          <component :is="showApiKeyModel ? Eye : EyeOff" class="h-4 w-4" />
        </button>
      </div>
    </div>

    <div class="space-y-1.5">
      <label class="block text-sm font-medium text-[var(--color-text-secondary)]">默认模型名称</label>
      <input
        v-model="draft.llm.defaultModel"
        type="text"
        class="input w-full"
        placeholder="例如: gpt-3.5-turbo"
      />
    </div>

    <div class="space-y-1.5">
      <label class="block text-sm font-medium text-[var(--color-text-secondary)]">MVU Agent 模型</label>
      <ModernSelect
        :model-value="draft.mvuModel ?? ''"
        :options="mvuModelOptions"
        placeholder="留空则使用默认模型名称与候选回退"
        class="w-full"
        searchable
        allow-create
        @select="emit('mvu-model-select', $event)"
      />
      <p class="text-xs text-[var(--color-text-muted)]">
        MVU 后台与 SillyTavern directive 导入兼容共用此模型；无需进入会话即可配置。
      </p>
    </div>
  </SettingsDrawerGlobalAccordion>
</template>
