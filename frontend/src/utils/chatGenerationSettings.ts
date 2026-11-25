import type { ApiPreset, ChatOverrides, GenerationParams, Settings } from '../types/models'
import { isTtsApiPreset } from './apiPresetKind'

type GenerationOverrides = Pick<ChatOverrides, 'params' | 'presetId'>
export type ChatGenerationField = 'temperature' | 'top_p' | 'max_tokens' | 'context_size'

export function normalizeChatContextSize(value: unknown): number | null {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) return null
  return Math.floor(value)
}

/** 复用生成请求的选取顺序。此处只描述设置绑定，不发请求或校验线上凭据。 */
export function resolveChatConnection(settings: Settings, overrides?: GenerationOverrides | null) {
  const overrideModel = overrides?.params?.model
  const model = ((overrideModel ?? settings.generationDefaults.model) || settings.llm.defaultModel || '').trim()
  return resolveModelConnection(settings, model, overrides?.presetId)
}

export function resolveModelConnection(settings: Settings, model: string, presetId?: string | null) {
  const explicitId = presetId?.trim()
  const presets = settings.apiPresets ?? []

  function describePreset(preset: ApiPreset) {
    const authStyle = preset.authStyle ?? ''
    const issue = isTtsApiPreset(preset)
      ? '语音预设不能用于文本生成'
      : !preset.baseUrl?.trim()
        ? '缺少 Base URL'
        : !preset.apiKey?.trim() && !authStyle.startsWith('oauth')
          ? '缺少 API Key'
          : null
    return { model, presetId: preset.id, connection: preset.name, issue, configured: issue == null }
  }

  if (explicitId) {
    const preset = presets.find(item => item.id === explicitId)
    if (preset) return describePreset(preset)
    return { model, presetId: explicitId, connection: 'API 预设不可用', issue: '预设已不存在', configured: false }
  }

  const llmPresets = presets.filter(preset => !isTtsApiPreset(preset))
  const modelPreset = model && llmPresets.find(preset => (preset.models ?? []).some(name => name.trim() === model))
  if (modelPreset) return describePreset(modelPreset)
  if (settings.llm.baseUrl?.trim() && settings.llm.apiKey?.trim()) {
    return { model, presetId: null, connection: '全局连接', issue: null, configured: true }
  }
  const fallback = llmPresets.find(preset => preset.baseUrl?.trim() && preset.apiKey?.trim())
  if (fallback) return describePreset(fallback)
  return { model, presetId: null, connection: '未配置可用连接', issue: null, configured: false }
}

export function formatChatGenerationField(defaults: GenerationParams, params: GenerationParams | undefined, key: ChatGenerationField) {
  const numeric = (value: unknown) => typeof value === 'number' && Number.isFinite(value) ? value : null
  const normalize = key === 'context_size' ? normalizeChatContextSize : numeric
  const override = normalize(params?.[key])
  const value = override ?? normalize(defaults[key])
  if (key === 'context_size' && override === 0) return '已关闭'
  const source = override == null ? '沿用全局' : '会话覆盖'
  if (key === 'context_size' && (value == null || value === 0)) return `${source} · 不限`
  if (value == null) return `${source} · 模型默认`
  const unit = key === 'context_size' || key === 'max_tokens' ? ' tokens' : ''
  return `${source} · ${value}${unit}`
}
