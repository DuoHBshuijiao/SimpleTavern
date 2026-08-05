/**
 * Anthropic prompt cache TTL（与后端 normalize_anthropic_prompt_cache 对齐）。
 * 仅 protocol=anthropic_messages 时有意义；默认 off。
 */
export const ANTHROPIC_PROMPT_CACHE_VALUES = ['off', '5m', '1h'] as const

export type AnthropicPromptCache = (typeof ANTHROPIC_PROMPT_CACHE_VALUES)[number]

export const DEFAULT_ANTHROPIC_PROMPT_CACHE: AnthropicPromptCache = 'off'

export const ANTHROPIC_PROMPT_CACHE_OPTIONS: Array<{ label: string; value: AnthropicPromptCache }> = [
  { label: '关闭（默认）', value: 'off' },
  { label: '5 分钟', value: '5m' },
  { label: '1 小时', value: '1h' },
]

/** 布尔 legacy true→5m、false→off；未知回落默认。 */
export function normalizeAnthropicPromptCache(raw: unknown): AnthropicPromptCache {
  if (typeof raw === 'boolean') return raw ? '5m' : 'off'
  if (typeof raw !== 'string') return DEFAULT_ANTHROPIC_PROMPT_CACHE
  const key = raw.trim().toLowerCase()
  if (!key) return DEFAULT_ANTHROPIC_PROMPT_CACHE
  if (key === 'true' || key === '1' || key === 'yes' || key === 'on' || key === 'enabled') return '5m'
  if (key === 'false' || key === '0' || key === 'no' || key === 'off' || key === 'disabled') return 'off'
  if ((ANTHROPIC_PROMPT_CACHE_VALUES as readonly string[]).includes(key)) {
    return key as AnthropicPromptCache
  }
  return DEFAULT_ANTHROPIC_PROMPT_CACHE
}
