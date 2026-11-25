import { onBeforeUnmount, shallowReactive, watch } from 'vue'
import type { ChatContentRegexRule } from '../types/models'

const DISPLAY_TIMEOUT_MS = 200

export function useContentRegexDisplay(getRules: () => ChatContentRegexRule[] | null | undefined) {
  const pending = new Map<string, string>()
  const results = shallowReactive(new Map<string, { raw: string; display: string }>())
  let worker: Worker | null = null
  let timer: ReturnType<typeof setTimeout> | undefined
  let inFlight: [id: string, raw: string] | undefined
  let rules: ChatContentRegexRule[] = []
  let scheduled = false

  function resetWorker() {
    clearTimeout(timer)
    worker?.terminate()
    worker = null
    inFlight = undefined
  }

  function processNext() {
    scheduled = false
    if (inFlight || !rules.length) return
    const item = pending.entries().next().value
    if (!item) return
    const [id, raw] = item
    pending.delete(id)
    inFlight = item

    function complete(display: string, restartWorker = false) {
      if (inFlight !== item) return
      clearTimeout(timer)
      if (restartWorker) resetWorker()
      inFlight = undefined
      results.set(id, { raw, display })
      scheduleNext()
    }

    try {
      worker ??= new Worker(new URL('../utils/contentRegex.worker.ts', import.meta.url), { type: 'module' })
      worker.onmessage = (event: MessageEvent<string>) => complete(event.data)
      worker.onerror = () => complete(raw, true)
      timer = setTimeout(() => complete(raw, true), DISPLAY_TIMEOUT_MS)
      worker.postMessage({ text: raw, rules })
    } catch {
      complete(raw, true)
    }
  }

  function scheduleNext() {
    if (scheduled) return
    scheduled = true
    queueMicrotask(processNext)
  }

  watch(() => {
    // 保存会话或设置会重建规则对象，按影响正文显示的字段判断缓存是否失效。
    const displayRules = (getRules() ?? [])
      .filter((rule) => rule.enabled !== false && rule.action !== 'extract' && rule.pattern.trim())
      .map(({ id, order, pattern, action, replacement, matchMode }) => ({
        id,
        order,
        pattern,
        action,
        replacement: replacement ?? '',
        matchMode: matchMode ?? 'global',
        enabled: true,
      }))
    return JSON.stringify(displayRules)
  }, (serializedRules) => {
    resetWorker()
    pending.clear()
    results.clear()
    rules = JSON.parse(serializedRules)
  }, { immediate: true, flush: 'sync' })

  onBeforeUnmount(() => {
    resetWorker()
    pending.clear()
  })

  return (id: string, raw: string) => {
    if (!raw || !rules.length) return raw
    const cached = results.get(id)
    if (cached?.raw === raw) return cached.display
    if (inFlight?.[0] !== id || inFlight[1] !== raw) {
      pending.set(id, raw)
      scheduleNext()
    }
    return raw
  }
}
