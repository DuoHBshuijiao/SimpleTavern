import type { ApiPreset, TtsProvider } from '../types/models'

/** TTS 服务 API 预设（如 MiniMax），不应出现在文字模型选择列表中。 */
export function isTtsApiPreset(preset?: ApiPreset | null): boolean {
  return preset?.presetKind === 'tts' || preset?.presetKind === 'minimax'
}

export function resolveTtsProvider(preset?: Pick<ApiPreset, 'ttsProvider'> | null): TtsProvider {
  if (preset?.ttsProvider === 'glm') return 'glm'
  if (preset?.ttsProvider === 'glm_local') return 'glm_local'
  if (preset?.ttsProvider === 'qwen3_local') return 'qwen3_local'
  if (preset?.ttsProvider === 'omnivoice_local') return 'omnivoice_local'
  if (preset?.ttsProvider === 'openrouter') return 'openrouter'
  if (preset?.ttsProvider === 'siliconflow') return 'siliconflow'
  return 'minimax'
}
