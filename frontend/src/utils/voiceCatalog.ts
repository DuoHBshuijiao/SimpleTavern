import type { ApiPresetVoice } from '../types/models'

/** 按 voiceId 去重并规范化 TTS 音色目录字段。 */
export function normalizeVoiceCatalog(voices?: ApiPresetVoice[] | null): ApiPresetVoice[] {
  const next = new Map<string, ApiPresetVoice>()
  for (const voice of voices || []) {
    const voiceId = String(voice.voiceId || '').trim()
    if (!voiceId) continue
    const promptText =
      voice.promptText != null && String(voice.promptText).trim()
        ? String(voice.promptText).trim()
        : null
    const promptAudioPath =
      voice.promptAudioPath != null && String(voice.promptAudioPath).trim()
        ? String(voice.promptAudioPath).trim()
        : null
    const instruction =
      voice.instruction != null && String(voice.instruction).trim()
        ? String(voice.instruction).trim()
        : null
    next.set(voiceId, {
      voiceId,
      name: String(voice.name || voiceId).trim() || voiceId,
      voiceType: String(voice.voiceType || 'system').trim() || 'system',
      promptText,
      promptAudioPath,
      instruction,
    })
  }
  return [...next.values()]
}
