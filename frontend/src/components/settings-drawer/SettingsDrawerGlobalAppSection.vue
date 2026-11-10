<script setup lang="ts">
import SettingsDrawerGlobalAccordion from './SettingsDrawerGlobalAccordion.vue'
import SettingsDrawerGlobalUsageSummary from './SettingsDrawerGlobalUsageSummary.vue'

defineProps<{
  appVersion: string
  checkUpdateLoading: boolean
  checkUpdateMessage: string
  chatId: string | null
}>()

const open = defineModel<boolean>('open', { required: true })

const emit = defineEmits<{
  'check-update': []
  'open-http-log': []
}>()
</script>

<template>
  <SettingsDrawerGlobalAccordion v-model:open="open" title="应用与更新">
    <SettingsDrawerGlobalUsageSummary :chat-id="chatId" />
    <div class="settings-group">
      <div class="settings-group-title">工具</div>
      <div class="flex flex-wrap items-center gap-2">
        <a
          href="https://duohbshuijiao.github.io/SumOrNot/"
          target="_blank"
          rel="noopener noreferrer"
          class="btn btn-sm btn-secondary"
        >
          成本计算器
        </a>
        <button type="button" class="btn btn-sm btn-secondary" @click="emit('open-http-log')">
          查看 HTTP 请求
        </button>
        <button
          type="button"
          class="btn btn-sm btn-secondary"
          :disabled="checkUpdateLoading"
          @click="emit('check-update')"
        >
          检查更新
        </button>
      </div>
      <p v-if="checkUpdateMessage" class="settings-hint">{{ checkUpdateMessage }}</p>
      <a
        href="https://github.com/DuoHBshuijiao/SimpleTavern/releases"
        target="_blank"
        rel="noopener noreferrer"
        class="settings-hint self-start cursor-pointer transition-colors hover:text-[var(--color-text-secondary)] hover:underline"
      >{{ appVersion || '…' }}</a>
    </div>
  </SettingsDrawerGlobalAccordion>
</template>
