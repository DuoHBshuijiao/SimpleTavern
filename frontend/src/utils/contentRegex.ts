/**
 * 前端正文正则处理——唯一入口，覆盖 remove / replace / extract_and_replace。
 * extract 仅用于 MVU 提取（后端 scanner 处理），不影响显示。
 * content 永远存原文，前端渲染时即时处理。
 */
import type { ChatContentRegexRule } from '../types/models'

const RULE_TIMEOUT_MS = 150

interface CompiledRule {
  regex: RegExp
  action: string
  replacement: string
  matchMode: string
}

function compileRule(rule: ChatContentRegexRule): CompiledRule | null {
  const pattern = (rule.pattern || '').trim()
  if (!pattern) return null
  try {
    if (pattern.startsWith('/')) {
      const lastSlash = pattern.lastIndexOf('/')
      if (lastSlash > 0) {
        const flags = pattern.slice(lastSlash + 1)
        const body = pattern.slice(1, lastSlash)
        return {
          regex: new RegExp(body, flags),
          action: rule.action || 'remove',
          replacement: rule.replacement || '',
          matchMode: rule.matchMode || 'global',
        }
      }
    }
  } catch { /* invalid regex */ }
  try {
    return {
      regex: new RegExp(pattern, 'gims'),
      action: rule.action || 'remove',
      replacement: rule.replacement || '',
      matchMode: rule.matchMode || 'global',
    }
  } catch {
    return null
  }
}

function replacementFor(action: string, ruleReplacement: string): string {
  if (action === 'remove') return ''
  return ruleReplacement || ''
}

/**
 * 对文本依次应用正文正则规则（remove / replace / extract_and_replace），返回显示文本。
 * extract 不影响文本。
 */
export function applyContentRegexDisplay(
  text: string,
  rules: ChatContentRegexRule[] | null | undefined,
): string {
  if (!text || !rules || rules.length === 0) return text

  const ordered = [...rules]
    .filter((r) => r.enabled !== false && (r.pattern || '').trim())
    .sort((a, b) => (a.order ?? 0) - (b.order ?? 0) || (a.id ?? '').localeCompare(b.id ?? ''))

  let working = text
  for (const rule of ordered) {
    if (rule.action === 'extract') continue
    const compiled = compileRule(rule)
    if (!compiled) continue

    const { regex, matchMode } = compiled
    const replacement = replacementFor(rule.action || 'remove', compiled.replacement)
    const start = performance.now()
    try {
      if (matchMode === 'first') {
        const match = regex.exec(working)
        if (match) {
          working = working.slice(0, match.index) + match[0].replace(regex, replacement) + working.slice(match.index + match[0].length)
        }
      } else {
        if (performance.now() - start > RULE_TIMEOUT_MS) continue
        regex.lastIndex = 0
        working = working.replace(regex, replacement)
      }
    } catch {
      continue
    }
  }
  return working
}
