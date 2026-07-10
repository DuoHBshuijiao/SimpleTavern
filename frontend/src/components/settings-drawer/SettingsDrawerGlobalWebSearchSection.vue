<script setup lang="ts">
import ModernSelect from '../ModernSelect.vue'
import WebSearchQuotaSummary from '../WebSearchQuotaSummary.vue'
import SettingsDrawerGlobalAccordion from './SettingsDrawerGlobalAccordion.vue'
import type { Settings, WebSearchProvider } from '../../types/models'

const WEB_SEARCH_PROVIDER_OPTIONS: Array<{ label: string; value: WebSearchProvider }> = [
  { label: 'Tavily', value: 'tavily' },
  { label: '博查（国内）', value: 'bocha' },
]

defineProps<{
  draft: Settings
  remoteStatus: Record<string, unknown> | null
  remoteStatusFetching: boolean
}>()

const open = defineModel<boolean>('open', { required: true })
</script>

<template>
  <SettingsDrawerGlobalAccordion v-model:open="open" title="网络搜索" content-class="space-y-5">
    <p class="text-xs text-[var(--color-text-muted)]">
      主聊天输入区可通过开关启用搜索（开启后每次发送均生效，直至关闭）；此处配置第三方 Search API。用量与余额在打开本抽屉时自动查询。
    </p>
    <div v-if="draft.webSearch" class="space-y-4">
      <div class="space-y-1.5">
        <label class="block text-sm font-medium text-[var(--color-text-secondary)]">提供方</label>
        <ModernSelect
          v-model="draft.webSearch.provider"
          :options="WEB_SEARCH_PROVIDER_OPTIONS"
          placeholder="选择搜索提供方…"
          class="w-full"
        />
      </div>
      <template v-if="draft.webSearch.provider === 'tavily' && draft.webSearch.tavily">
        <div class="space-y-1.5">
          <label class="block text-sm font-medium text-[var(--color-text-secondary)]">Tavily API Key</label>
          <input
            v-model="draft.webSearch.tavily.apiKey"
            type="password"
            autocomplete="off"
            class="input w-full"
            placeholder="tvly-..."
          />
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div class="space-y-1.5">
            <label class="block text-xs text-[var(--color-text-muted)]">max_results（0–20）</label>
            <input
              v-model.number="draft.webSearch.tavily.max_results"
              type="number"
              min="0"
              max="20"
              class="input w-full"
            />
          </div>
          <div class="space-y-1.5">
            <label class="block text-xs text-[var(--color-text-muted)]">search_depth</label>
            <input
              v-model="draft.webSearch.tavily.search_depth"
              type="text"
              class="input w-full"
              placeholder="basic / advanced / fast …"
            />
          </div>
        </div>
      </template>
      <template v-else-if="draft.webSearch.bocha">
        <div class="space-y-1.5">
          <label class="block text-sm font-medium text-[var(--color-text-secondary)]">博查 API Key</label>
          <input
            v-model="draft.webSearch.bocha.apiKey"
            type="password"
            autocomplete="off"
            class="input w-full"
          />
        </div>
        <div class="space-y-1.5">
          <label class="block text-sm font-medium text-[var(--color-text-secondary)]">API 根地址</label>
          <input
            v-model="draft.webSearch.bocha.baseUrl"
            type="text"
            class="input w-full"
            placeholder="https://api.bocha.cn"
          />
        </div>
        <div class="space-y-1.5">
          <label class="block text-sm font-medium text-[var(--color-text-secondary)]">count（1–50）</label>
          <input
            v-model.number="draft.webSearch.bocha.count"
            type="number"
            min="1"
            max="50"
            class="input w-full"
          />
        </div>
      </template>
      <div
        class="rounded-lg border border-[var(--color-border-subtle)] bg-[var(--color-settings-control-bg)] p-3 text-xs text-[var(--color-text-muted)] transition-opacity duration-200"
        :class="remoteStatusFetching ? 'opacity-70' : ''"
      >
        <div class="mb-1 flex items-center justify-between gap-2 font-medium text-[var(--color-text-secondary)]">
          <span>用量 / 余额</span>
          <span
            v-if="remoteStatusFetching"
            class="text-2xs font-normal text-[var(--color-text-muted)]"
          >
            刷新中…
          </span>
        </div>
        <WebSearchQuotaSummary :status="remoteStatus" :provider="draft.webSearch.provider" />
      </div>
    </div>
  </SettingsDrawerGlobalAccordion>
</template>
