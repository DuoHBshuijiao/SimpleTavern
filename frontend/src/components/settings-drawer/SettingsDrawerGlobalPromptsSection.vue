<script setup lang="ts">
import SettingsDrawerGlobalAccordion from './SettingsDrawerGlobalAccordion.vue'
import SettingsField from './SettingsField.vue'
import SettingsSwitch from './SettingsSwitch.vue'
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
  <SettingsDrawerGlobalAccordion v-model:open="open" title="提示词与生成参数">
    <div class="settings-group">
      <div class="settings-group-title">提示词</div>
      <SettingsField label="全局系统提示词">
        <textarea v-model="draft.prompts.globalSystem" rows="4" class="input textarea w-full resize-y" />
      </SettingsField>
      <div class="settings-field">
        <SettingsSwitch
          :model-value="!!draft.prompts.globalPrefillEnabled"
          label="预填内容"
          @update:model-value="(v) => { draft.prompts.globalPrefillEnabled = v }"
        />
        <textarea
          v-model="draft.prompts.globalPrefill"
          rows="2"
          class="input textarea w-full resize-y"
          placeholder="以助手身份附加在请求末尾，模型在其后续写；留空则不启用"
        />
      </div>
    </div>

    <div class="settings-group">
      <div class="settings-group-title">生成参数</div>
      <div class="grid grid-cols-2 gap-4">
        <SettingsField label="Temperature">
          <input
            v-model.number="draft.generationDefaults.temperature"
            type="number"
            step="0.1"
            min="0"
            max="2"
            placeholder="默认"
            class="input w-full"
          />
        </SettingsField>
        <SettingsField label="Top P">
          <input
            v-model.number="draft.generationDefaults.top_p"
            type="number"
            step="0.1"
            min="0"
            max="1"
            placeholder="默认"
            class="input w-full"
          />
        </SettingsField>
        <SettingsField label="最大输出长度">
          <input
            v-model.number="draft.generationDefaults.max_tokens"
            type="number"
            step="128"
            min="1"
            placeholder="默认"
            class="input w-full"
          />
        </SettingsField>
      </div>
    </div>

    <div class="settings-group">
      <div class="settings-group-title">上下文</div>
      <div class="grid grid-cols-2 gap-4">
        <SettingsField label="上下文长度" more="角色卡、用户信息和系统提示词不计入这个长度。">
          <input
            v-model.number="draft.generationDefaults.context_size"
            type="number"
            min="0"
            placeholder="未启用（默认不限制）"
            class="input w-full"
          />
        </SettingsField>
        <SettingsField label="草稿助手条数限制" more="只统计最近的消息条数；留空就按上下文长度处理。">
          <input
            :value="draft.draftHelpDefaults?.context_message_limit ?? ''"
            type="text"
            inputmode="numeric"
            pattern="[0-9]*"
            placeholder="未启用（跟随当前逻辑）"
            class="input w-full"
            @input="emit('draft-help-limit-input', $event)"
          />
        </SettingsField>
      </div>
    </div>
  </SettingsDrawerGlobalAccordion>
</template>
