import type { WorldBookEntry } from '../types/models'

/** 与后端 WorldBookEntry._validate_regex_if_needed 一致：非空正则须可编译 */
export function validateWorldBookEntry(d: WorldBookEntry): string | null {
  const pattern = (d.regex || '').trim()
  if (!pattern) return null
  try {
    // eslint-disable-next-line no-new
    new RegExp(pattern)
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e)
    return `invalid regex: ${msg}`
  }
  return null
}

export function formatApiError(err: unknown): string {
  const msg = err instanceof Error ? err.message : String(err)
  try {
    const j = JSON.parse(msg) as { detail?: unknown }
    const d = j.detail
    if (Array.isArray(d)) {
      return d
        .map((item: unknown) => {
          if (item && typeof item === 'object' && 'msg' in item) {
            return String((item as { msg: string }).msg)
          }
          return JSON.stringify(item)
        })
        .join('；')
    }
    if (typeof d === 'string') return d
    if (d != null) return JSON.stringify(d)
  } catch {
    /* 非 JSON */
  }
  return msg
}
