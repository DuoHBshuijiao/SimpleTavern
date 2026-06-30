<script setup lang="ts">
import SettingsDrawerGlobalAccordion from './SettingsDrawerGlobalAccordion.vue'
import type { Settings } from '../../types/models'

defineProps<{
  draft: Settings
}>()

const open = defineModel<boolean>('open', { required: true })

const emit = defineEmits<{
  'draft-help-limit-input': [event: Event]
}>()
</script>

<template>
  <SettingsDrawerGlobalAccordion v-model:open="open" title="提示词与生成参数" content-class="space-y-5">
    <div class="space-y-1.5">
      <label class="block text-sm font-medium text-[var(--color-text-secondary)]">全局系统提示词</label>
      <textarea v-model="draft.prompts.globalSystem" rows="4" class="input textarea w-full resize-y" />
    </div>

    <div class="space-y-2">
      <div class="flex items-center justify-between gap-3">
        <label class="block text-sm font-medium text-[var(--color-text-secondary)]">预填内容</label>
        <button
          type="button"
          class="group flex min-h-11 cursor-pointer items-center gap-3 py-1 text-left"
          @click="draft.prompts.globalPrefillEnabled = !draft.prompts.globalPrefillEnabled"
        >
          <div
            class="relative h-6 w-11 shrink-0 rounded-full transition-colors duration-200 ease-out"
            :class="draft.prompts.globalPrefillEnabled ? 'bg-brand' : 'bg-[var(--color-track)]'"
          >
            <div
              class="absolute left-1 top-1 h-4 w-4 rounded-full bg-[var(--color-on-brand)]"
              :style="{
                transform: draft.prompts.globalPrefillEnabled ? 'translateX(1.25rem)' : 'translateX(0)',
                transition: 'transform 200ms ease-out',
              }"
            />
          </div>
          <span class="text-xs text-[var(--color-text-secondary)]">
            {{
              draft.prompts.globalPrefillEnabled
                ? '已开启：发送请求时附加预填'
                : '已关闭：保留文案但暂不生效'
            }}
          </span>
        </button>
      </div>
      <textarea
        v-model="draft.prompts.globalPrefill"
        rows="2"
        class="input textarea w-full resize-y"
        placeholder="以助手身份附加在请求末尾，模型在其后续写；留空则不启用"
      />
    </div>

    <div class="grid grid-cols-2 gap-4 pt-2">
      <div class="space-y-1.5">
        <label class="block text-sm font-medium text-[var(--color-text-secondary)]">Temperature</label>
        <input
          v-model.number="draft.generationDefaults.temperature"
          type="number"
          step="0.1"
          min="0"
          max="2"
          placeholder="默认"
          class="input w-full"
        />
      </div>
      <div class="space-y-1.5">
        <label class="block text-sm font-medium text-[var(--color-text-secondary)]">Top P</label>
        <input
          v-model.number="draft.generationDefaults.top_p"
          type="number"
          step="0.1"
          min="0"
          max="1"
          placeholder="默认"
          class="input w-full"
        />
      </div>
      <div class="space-y-1.5">
        <label class="block text-sm font-medium text-[var(--color-text-secondary)]">最大输出长度</label>
        <input
          v-model.number="draft.generationDefaults.max_tokens"
          type="number"
          step="128"
          min="1"
          placeholder="默认"
          class="input w-full"
        />
      </div>
    </div>

    <div class="space-y-2 pt-2">
      <div class="text-sm font-medium text-[var(--color-text-secondary)]">上下文</div>
      <div class="grid grid-cols-2 gap-4">
        <div class="space-y-1.5">
          <label class="block text-sm font-medium text-[var(--color-text-secondary)]">上下文长度</label>
          <input
            v-model.number="draft.generationDefaults.context_size"
            type="number"
            min="0"
            placeholder="未启用（默认不限制）"
            class="input w-full"
          />
        </div>
        <div class="space-y-1.5">
          <label class="block text-sm font-medium text-[var(--color-text-secondary)]">草稿助手上下文条数限制</label>
          <input
            :value="draft.draftHelpDefaults?.context_message_limit ?? ''"
            type="text"
            inputmode="numeric"
            pattern="[0-9]*"
            placeholder="未启用（跟随当前逻辑）"
            class="input w-full"
            @input="emit('draft-help-limit-input', $event)"
          />
        </div>
      </div>
    </div>
    <p class="text-xs text-[var(--color-text-muted)]">
      实际上下文总限制长度为该「上下文长度」限制加上角色卡、用户信息、自定义系统提示词。草稿助手条数限制只统计最近消息条数，留空则回退到现有上下文逻辑。
    </p>
  </SettingsDrawerGlobalAccordion>
</template>
