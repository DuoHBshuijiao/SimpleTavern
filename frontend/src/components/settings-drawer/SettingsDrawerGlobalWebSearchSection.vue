<script setup lang="ts">
import { watch } from 'vue'
import ModernSelect from '../ModernSelect.vue'
import ThemedRadioTags from '../ThemedRadioTags.vue'
import WebSearchQuotaSummary from '../WebSearchQuotaSummary.vue'
import SettingsDrawerGlobalAccordion from './SettingsDrawerGlobalAccordion.vue'
import SettingsField from './SettingsField.vue'
import SettingsHint from './SettingsHint.vue'
import type { Settings, WebSearchProvider } from '../../types/models'

const WEB_SEARCH_PROVIDER_OPTIONS: Array<{ label: string; value: WebSearchProvider }> = [
  { label: 'Tavily', value: 'tavily' },
  { label: '博查（国内）', value: 'bocha' },
  { label: 'Brave Search', value: 'brave' },
]

const GEMINI_SEARCH_OPTIONS = [
  { label: '原生 Google Search', value: 'native' },
  { label: '第三方（Tavily / 博查 / Brave）', value: 'independent' },
]

const props = defineProps<{
  draft: Settings
  remoteStatus: Record<string, unknown> | null
  remoteStatusFetching: boolean
}>()

const open = defineModel<boolean>('open', { required: true })

watch(
  () => props.draft.webSearch,
  (ws) => {
    if (ws && !ws.brave) ws.brave = { apiKey: '' }
    if (ws && !ws.geminiSearch) ws.geminiSearch = 'native'
  },
  { immediate: true },
)
</script>

<template>
  <SettingsDrawerGlobalAccordion v-model:open="open" title="网络搜索">
    <div class="settings-group">
      <SettingsHint more="独立搜索供应商（Tavily / 博查 / Brave，走本地工具循环）与模型原生联网。OpenAI Responses / Anthropic Messages 打开搜索后走厂商原生。Gemini 必须在下方显式选择「原生 Google Search」或「第三方」；选第三方时需要独立搜索 API Key。">
        独立搜索供应商与模型原生联网互不自动切换。
      </SettingsHint>
      <template v-if="draft.webSearch">
        <SettingsField label="Gemini 搜索来源">
          <ThemedRadioTags
            :model-value="draft.webSearch.geminiSearch || 'native'"
            :options="GEMINI_SEARCH_OPTIONS"
            aria-label="Gemini 搜索来源"
            @update:model-value="(v) => { if (draft.webSearch) draft.webSearch.geminiSearch = v as 'native' | 'independent' }"
          />
        </SettingsField>
        <SettingsField label="提供方">
          <ModernSelect
            v-model="draft.webSearch.provider"
            :options="WEB_SEARCH_PROVIDER_OPTIONS"
            placeholder="选择搜索提供方…"
            class="w-full"
          />
        </SettingsField>
        <template v-if="draft.webSearch.provider === 'tavily' && draft.webSearch.tavily">
          <SettingsField label="Tavily API Key">
            <input
              v-model="draft.webSearch.tavily.apiKey"
              type="password"
              autocomplete="off"
              class="input w-full"
              placeholder="tvly-..."
            />
          </SettingsField>
          <div class="grid grid-cols-2 gap-3">
            <SettingsField label="max_results（0–20）">
              <input
                v-model.number="draft.webSearch.tavily.max_results"
                type="number"
                min="0"
                max="20"
                class="input w-full"
              />
            </SettingsField>
            <SettingsField label="search_depth">
              <input
                v-model="draft.webSearch.tavily.search_depth"
                type="text"
                class="input w-full"
                placeholder="basic / advanced / fast …"
              />
            </SettingsField>
          </div>
        </template>
        <template v-else-if="draft.webSearch.provider === 'brave' && draft.webSearch.brave">
          <SettingsField label="Brave Subscription Token">
            <input
              v-model="draft.webSearch.brave.apiKey"
              type="password"
              autocomplete="off"
              class="input w-full"
              placeholder="BSA..."
            />
          </SettingsField>
          <SettingsField label="count（1–20）">
            <input
              v-model.number="draft.webSearch.brave.count"
              type="number"
              min="1"
              max="20"
              class="input w-full"
            />
          </SettingsField>
        </template>
        <template v-else-if="draft.webSearch.bocha">
          <SettingsField label="博查 API Key">
            <input
              v-model="draft.webSearch.bocha.apiKey"
              type="password"
              autocomplete="off"
              class="input w-full"
            />
          </SettingsField>
          <SettingsField label="API 根地址">
            <input
              v-model="draft.webSearch.bocha.baseUrl"
              type="text"
              class="input w-full"
              placeholder="https://api.bocha.cn"
            />
          </SettingsField>
          <SettingsField label="count（1–50）">
            <input
              v-model.number="draft.webSearch.bocha.count"
              type="number"
              min="1"
              max="50"
              class="input w-full"
            />
          </SettingsField>
        </template>
        <div
          class="settings-readout transition-opacity duration-200"
          :class="remoteStatusFetching ? 'opacity-70' : ''"
        >
          <div class="mb-1 flex items-center justify-between gap-2 font-medium text-[var(--color-text-secondary)]">
            <span>用量 / 余额</span>
            <span v-if="remoteStatusFetching" class="font-normal text-[var(--color-text-muted)]">刷新中…</span>
          </div>
          <WebSearchQuotaSummary :status="remoteStatus" :provider="draft.webSearch.provider" />
        </div>
      </template>
    </div>
  </SettingsDrawerGlobalAccordion>
</template>
