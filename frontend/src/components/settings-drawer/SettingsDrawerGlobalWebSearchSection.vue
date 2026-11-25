<script setup lang="ts">
import { computed, ref, useId, watch } from 'vue'
import { ChevronDown } from 'lucide-vue-next'
import ModernSelect from '../ModernSelect.vue'
import ThemedRadioTags from '../ThemedRadioTags.vue'
import WebSearchQuotaSummary from '../WebSearchQuotaSummary.vue'
import SettingsDrawerGlobalAccordion from './SettingsDrawerGlobalAccordion.vue'
import SettingsField from './SettingsField.vue'
import type { Settings, WebSearchProvider, WebSearchSource } from '../../types/models'

const WEB_SEARCH_PROVIDER_OPTIONS: Array<{ label: string; value: WebSearchProvider }> = [
  { label: 'Tavily', value: 'tavily' },
  { label: '博查（国内）', value: 'bocha' },
  { label: 'Brave Search', value: 'brave' },
]

const SEARCH_SOURCE_OPTIONS = [
  { label: '供应商原生', value: 'native' },
  { label: '第三方搜索', value: 'independent' },
]

const props = defineProps<{
  draft: Settings
  remoteStatus: Record<string, unknown> | null
  remoteStatusFetching: boolean
  remoteStatusError: boolean
}>()

const open = defineModel<boolean>('open', { required: true })
const thirdPartyId = useId()
const thirdPartyExpanded = ref(false)
const usesNativeSearch = computed(() => props.draft.webSearch?.source === 'native')

watch(usesNativeSearch, () => {
  thirdPartyExpanded.value = false
})

watch(
  () => props.draft.webSearch,
  (ws) => {
    if (ws && !ws.brave) ws.brave = { apiKey: '' }
  },
  { immediate: true },
)
</script>

<template>
  <SettingsDrawerGlobalAccordion v-model:open="open" title="网络搜索">
    <div class="settings-group">
      <template v-if="draft.webSearch">
        <SettingsField label="联网来源" more="原生搜索使用当前模型的联网工具。「第三方搜索配置」也可供 API 预设单独使用。">
          <ThemedRadioTags
            :model-value="draft.webSearch.source || ''"
            :options="SEARCH_SOURCE_OPTIONS"
            aria-label="联网来源"
            @update:model-value="(v) => { if (draft.webSearch) draft.webSearch.source = v as WebSearchSource }"
          />
        </SettingsField>
        <button
          v-if="usesNativeSearch"
          type="button"
          class="btn btn-sm btn-secondary self-start"
          :aria-expanded="thirdPartyExpanded"
          :aria-controls="thirdPartyId"
          @click="thirdPartyExpanded = !thirdPartyExpanded"
        >
          第三方搜索配置
          <ChevronDown aria-hidden="true" class="h-4 w-4" :class="{ 'rotate-180': thirdPartyExpanded }" />
        </button>
        <div :id="thirdPartyId" v-show="!usesNativeSearch || thirdPartyExpanded" class="flex flex-col gap-4">
          <SettingsField label="第三方搜索供应商">
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
              <SettingsField label="结果上限（0–20）">
                <input
                  v-model.number="draft.webSearch.tavily.max_results"
                  type="number"
                  min="0"
                  max="20"
                  class="input w-full"
                />
              </SettingsField>
              <SettingsField label="搜索深度">
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
            <SettingsField label="结果上限（1–20）">
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
            <SettingsField label="结果上限（1–50）">
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
            <p v-if="remoteStatusError" role="status" class="text-[var(--color-warning-text,var(--color-warning))]">
              额度刷新失败。
            </p>
            <WebSearchQuotaSummary v-else :status="remoteStatus" :provider="draft.webSearch.provider" />
          </div>
        </div>
      </template>
    </div>
  </SettingsDrawerGlobalAccordion>
</template>
