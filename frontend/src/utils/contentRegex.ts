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

const SAFE_LITERAL_FLAGS = new Set(['g', 'i', 'm', 's', 'u'])

function splitRegexLiteral(raw: string): { body: string; flags: string } | null {
  const text = (raw || '').trim()
  if (text.length < 2 || !text.startsWith('/')) return null

  let inClass = false
  let index = 1
  while (index < text.length) {
    const ch = text[index]
    if (ch === '\\') {
      index += 2
      continue
    }
    if (ch === '[' && !inClass) {
      inClass = true
      index += 1
      continue
    }
    if (ch === ']' && inClass) {
      inClass = false
      index += 1
      continue
    }
    if (ch === '/' && !inClass) {
      const body = text.slice(1, index)
      const flags = text.slice(index + 1).toLowerCase()
      if (flags && !/^[a-z]+$/.test(flags)) return null
      const seen = new Set<string>()
      for (const flag of flags) {
        if (seen.has(flag) || !SAFE_LITERAL_FLAGS.has(flag)) return null
        seen.add(flag)
      }
      return { body, flags }
    }
    index += 1
  }
  return null
}

function withRuntimeFlags(flags: string, matchMode: string): string {
  const out = new Set<string>(['m', 's'])
  for (const flag of flags) out.add(flag)
  if ((matchMode || 'global') === 'global') out.add('g')
  return [...out].join('')
}

function toJsReplacement(replacement: string): string {
  return (replacement || '').replace(/\\g<(\d+)>/g, '$$$1')
}

function compileRule(rule: ChatContentRegexRule): CompiledRule | null {
  const pattern = (rule.pattern || '').trim()
  if (!pattern) return null
  const matchMode = rule.matchMode || 'global'
  try {
    const literal = splitRegexLiteral(pattern)
    if (literal) {
      return {
        regex: new RegExp(literal.body, withRuntimeFlags(literal.flags, matchMode)),
        action: rule.action || 'remove',
        replacement: toJsReplacement(rule.replacement || ''),
        matchMode,
      }
    }
  } catch { /* invalid regex */ }
  try {
    return {
      regex: new RegExp(pattern, withRuntimeFlags('', matchMode)),
      action: rule.action || 'remove',
      replacement: toJsReplacement(rule.replacement || ''),
      matchMode,
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
        regex.lastIndex = 0
        working = working.replace(regex, replacement)
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
