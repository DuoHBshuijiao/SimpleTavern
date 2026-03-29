const SAFE_REGEX_LITERAL_FLAGS = new Set(['i', 'm', 's', 'u'])

export interface ParsedRegexInput {
  pattern: string
  flags: string
  normalizedFromLiteral: boolean
}

export function parseRegexInput(raw: string): ParsedRegexInput {
  const text = (raw || '').trim()
  if (text.length < 2 || text[0] !== '/') {
    return { pattern: text, flags: '', normalizedFromLiteral: false }
  }

  let inClass = false
  for (let idx = 1; idx < text.length; idx += 1) {
    const ch = text[idx]
    if (ch === '\\') {
      idx += 1
      continue
    }
    if (ch === '[' && !inClass) {
      inClass = true
      continue
    }
    if (ch === ']' && inClass) {
      inClass = false
      continue
    }
    if (ch === '/' && !inClass) {
      const pattern = text.slice(1, idx)
      const suffix = text.slice(idx + 1)
      if (suffix && !/^[a-z]+$/i.test(suffix)) break

      let flags = ''
      const seen = new Set<string>()
      for (const rawFlag of suffix.toLowerCase()) {
        if (seen.has(rawFlag) || !SAFE_REGEX_LITERAL_FLAGS.has(rawFlag)) {
          return { pattern: text, flags: '', normalizedFromLiteral: false }
        }
        seen.add(rawFlag)
        flags += rawFlag
      }
      return { pattern, flags, normalizedFromLiteral: true }
    }
  }

  return { pattern: text, flags: '', normalizedFromLiteral: false }
}

export function buildRegexFromInput(raw: string): RegExp {
  const parsed = parseRegexInput(raw)
  return new RegExp(parsed.pattern, parsed.flags)
}
