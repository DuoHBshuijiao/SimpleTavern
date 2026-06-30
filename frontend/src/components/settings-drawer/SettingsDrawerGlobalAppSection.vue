<script setup lang="ts">
import SettingsDrawerGlobalAccordion from './SettingsDrawerGlobalAccordion.vue'

defineProps<{
  appVersion: string
  checkUpdateLoading: boolean
  checkUpdateMessage: string
}>()

const open = defineModel<boolean>('open', { required: true })

const emit = defineEmits<{
  'check-update': []
  'open-http-log': []
}>()
</script>

<template>
  <SettingsDrawerGlobalAccordion v-model:open="open" title="应用与更新">
    <div class="flex flex-wrap items-center gap-2">
      <a
        href="https://duohbshuijiao.github.io/SumOrNot/"
        target="_blank"
        rel="noopener noreferrer"
        class="inline-flex min-h-10 items-center whitespace-nowrap rounded-lg bg-surface-muted px-4 py-2 text-sm text-[var(--color-text)] transition-colors hover:bg-surface-hover"
      >
        成本计算器
      </a>
    </div>
    <div class="flex flex-wrap items-center gap-2">
      <button
        type="button"
        class="min-h-10 whitespace-nowrap rounded-lg bg-surface-muted px-4 py-2 text-sm text-[var(--color-text)] transition-colors hover:bg-surface-hover"
        @click="emit('open-http-log')"
      >
        查看 HTTP 请求
      </button>
      <span class="text-xs text-[var(--color-text-muted)]">最近 30 分钟云端请求</span>
    </div>
    <div class="flex flex-wrap items-center gap-2">
      <button
        type="button"
        class="min-h-10 whitespace-nowrap rounded-lg bg-surface-muted px-4 py-2 text-sm text-[var(--color-text)] transition-colors hover:bg-surface-hover"
        :disabled="checkUpdateLoading"
        @click="emit('check-update')"
      >
        检查更新
      </button>
      <span v-if="checkUpdateMessage" class="text-xs text-[var(--color-text-secondary)]">{{
        checkUpdateMessage
      }}</span>
    </div>
    <a
      href="https://github.com/DuoHBshuijiao/SimpleTavern/releases"
      target="_blank"
      rel="noopener noreferrer"
      class="block cursor-pointer text-center text-xs text-[var(--color-text-muted)] transition-colors hover:text-[var(--color-text-secondary)] hover:underline"
    >{{ appVersion || '…' }}</a>
  </SettingsDrawerGlobalAccordion>
</template>
