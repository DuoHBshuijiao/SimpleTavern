import { describe, expect, it } from 'vitest'
import { catalogProviderToPreset, groupProviderPresets, type LlmProviderPreset } from './llmProviderPresets'
import type { LlmCatalogProvider } from '../api/llm'

const sample: LlmCatalogProvider = {
  id: 'deepseek',
  piId: 'deepseek',
  label: 'DeepSeek',
  name: 'DeepSeek',
  region: 'cn',
  group: 'cn',
  baseUrlTemplate: 'https://api.deepseek.com/v1',
  placeholders: [],
  authStyle: 'bearer',
  defaultProtocol: 'auto',
  supportedProtocols: ['openai_compatible_chat', 'openai_responses', 'anthropic_messages'],
  protocolVariant: null,
  protocolPaths: {},
  cacheStrategy: 'best_effort',
  explicitCacheMarkers: false,
  fastMode: null,
  docsUrl: null,
  keywords: ['deepseek'],
  legacyIds: ['deepseek'],
  requiresOAuth: false,
  hint: null,
  envKeys: [],
  unsupportedApis: [],
  suggestedModels: ['deepseek-v4-flash'],
}

describe('llmProviderPresets', () => {
  it('catalogProviderToPreset 保留分组、协议与缓存徽标字段', () => {
    const p = catalogProviderToPreset(sample)
    expect(p.providerId).toBe('deepseek')
    expect(p.group).toBe('cn')
    expect(p.supportedProtocols).toContain('anthropic_messages')
    expect(p.cacheStrategy).toBe('best_effort')
    expect(p.suggestedModels).toEqual(['deepseek-v4-flash'])
  })

  it('groupProviderPresets 按 国内 / 海外 / 网关 / OAuth 排序', () => {
    const list: LlmProviderPreset[] = [
      { id: 'oa', label: 'OpenAI', name: 'OpenAI', baseUrl: 'https://api.openai.com/v1', group: 'global' },
      { id: 'ds', label: 'DeepSeek', name: 'DeepSeek', baseUrl: 'https://api.deepseek.com/v1', group: 'cn' },
      { id: 'or', label: 'OpenRouter', name: 'OpenRouter', baseUrl: 'https://openrouter.ai/api/v1', group: 'gateway' },
    ]
    const grouped = groupProviderPresets(list)
    expect(grouped.map((g) => g.group)).toEqual(['cn', 'global', 'gateway'])
    expect(grouped[0]?.label).toBe('中国厂商')
  })
})
