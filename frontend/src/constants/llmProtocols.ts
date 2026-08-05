/**
 * LLM 协议标识（与后端 ProtocolId 对齐；未实现的协议会 fast-fail）。
 */
export const LLM_PROTOCOL_IDS = [
  'openai_compatible_chat',
  'anthropic_messages',
  'gemini_generate_content',
  'openai_responses',
] as const

export type LlmProtocolId = (typeof LLM_PROTOCOL_IDS)[number]

export const DEFAULT_LLM_PROTOCOL: LlmProtocolId = 'openai_compatible_chat'

export const LLM_PROTOCOL_OPTIONS: Array<{ label: string; value: LlmProtocolId }> = [
  { label: 'OpenAI Compatible Chat（默认）', value: 'openai_compatible_chat' },
  { label: 'Anthropic Messages（即将支持）', value: 'anthropic_messages' },
  { label: 'Gemini generateContent（即将支持）', value: 'gemini_generate_content' },
  { label: 'OpenAI Responses（即将支持）', value: 'openai_responses' },
]

export function normalizeLlmProtocol(raw: unknown): LlmProtocolId {
  const key = typeof raw === 'string' ? raw.trim() : ''
  if ((LLM_PROTOCOL_IDS as readonly string[]).includes(key)) {
    return key as LlmProtocolId
  }
  return DEFAULT_LLM_PROTOCOL
}
