import type { ApiPreset, ApiPresetVoice, TtsProvider } from '../types/models'

export const DEEPSEEK_TTS_BASE_URL = 'https://api.deepseek.com'
export const DEEPSEEK_TTS_VOICES: ApiPresetVoice[] = [
  { voiceId: 'stella', name: '海星', voiceType: 'system' },
  { voiceId: 'tide', name: '暗潮', voiceType: 'system' },
]

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
  if (preset?.ttsProvider === 'deepseek') return 'deepseek'
  return 'minimax'
}
