/**
 * LLM 协议标识（与后端 ProtocolId 对齐；未实现的协议会 fast-fail）。
 *
 * 归一化规则与后端 `normalize_protocol_id` 对齐：仅空值回落到默认；
 * 未知非空值原样保留，禁止静默改写成 compat。
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

/** 仅空/非法类型回落到默认；未知非空协议原样保留。 */
export function normalizeLlmProtocol(raw: unknown): string {
  const key = typeof raw === 'string' ? raw.trim() : ''
  if (!key) return DEFAULT_LLM_PROTOCOL
  return key
}

export function isKnownLlmProtocol(raw: unknown): raw is LlmProtocolId {
  const key = typeof raw === 'string' ? raw.trim() : ''
  return (LLM_PROTOCOL_IDS as readonly string[]).includes(key)
}

/** 下拉选项：若当前值为未知协议，追加一项以免保存时被 UI 冲掉。 */
export function llmProtocolSelectOptions(
  current?: string | null,
): Array<{ label: string; value: string }> {
  const opts: Array<{ label: string; value: string }> = LLM_PROTOCOL_OPTIONS.map((o) => ({
    label: o.label,
    value: o.value,
  }))
  const key = typeof current === 'string' ? current.trim() : ''
  if (key && !isKnownLlmProtocol(key)) {
    opts.push({ label: `未知协议（${key}）— 当前版本不支持`, value: key })
  }
  return opts
}
