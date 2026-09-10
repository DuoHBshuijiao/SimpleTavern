// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import LlmPresetNameCombobox from './LlmPresetNameCombobox.vue'
import { catalogProviderToPreset } from '../constants/llmProviderPresets'
import type { LlmCatalogProvider } from '../api/llm'

function provider(partial: Partial<LlmCatalogProvider> & Pick<LlmCatalogProvider, 'id' | 'label' | 'group'>): LlmCatalogProvider {
  return {
    piId: partial.id,
    name: partial.label,
    region: partial.group === 'cn' ? 'cn' : 'global',
    baseUrlTemplate: 'https://example.com/v1',
    placeholders: [],
    authStyle: 'bearer',
    defaultProtocol: 'openai_compatible_chat',
    supportedProtocols: ['openai_compatible_chat'],
    protocolVariant: null,
    protocolPaths: {},
    cacheStrategy: 'best_effort',
    explicitCacheMarkers: false,
    fastMode: null,
    docsUrl: null,
    keywords: [partial.id],
    legacyIds: [],
    requiresOAuth: false,
    hint: null,
    envKeys: [],
    unsupportedApis: [],
    suggestedModels: [],
    ...partial,
  }
}

describe('LlmPresetNameCombobox', () => {
  it('按分组列出供应商并显示协议徽标', async () => {
    const presets = [
      catalogProviderToPreset(provider({ id: 'deepseek', label: 'DeepSeek', group: 'cn', supportedProtocols: ['openai_compatible_chat', 'anthropic_messages'] })),
      catalogProviderToPreset(provider({ id: 'openai', label: 'OpenAI', group: 'global' })),
    ]
    const wrapper = mount(LlmPresetNameCombobox, {
      props: { modelValue: '', presets },
    })
    await wrapper.get('[aria-label="展开供应商列表"]').trigger('click')
    const list = wrapper.get('[data-testid="llm-provider-list"]')
    expect(list.text()).toContain('中国厂商')
    expect(list.text()).toContain('国际厂商')
    expect(list.text()).toContain('DeepSeek')
    expect(list.text()).toContain('Anthropic')
  })
})
