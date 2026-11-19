import { apiPost } from './http'
import type { ChatContentRegexRule } from '../types/models'

export interface ContentRegexPreview {
  beforeText: string
  afterText: string
  displayText: string
  changed: boolean
  extractedItems: Array<{ value: string; matchedText: string; ruleId: string }>
  errors: Array<{ ruleId: string; ruleName: string; errorCode: string; error: string }>
}

export function previewContentRegex(text: string, rules: ChatContentRegexRule[], signal?: AbortSignal) {
  return apiPost<ContentRegexPreview>('/api/settings/content-regex/preview', { text, rules }, signal)
}
