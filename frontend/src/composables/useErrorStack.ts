/**
 * 主聊天 / 助手流式错误栈（右下角 ErrorModal）。
 * 与 useNotify 分工：非阻塞业务提示、确认框走全局 AppNotificationHost，本栈保留自动消失与复制。
 */
import { ref } from 'vue'

export interface ErrorStackItem {
  id: string
  message: string
  source: 'main' | 'assistant'
  title: string
  createdAt: number
  timeoutMs: number
}

interface InternalErrorStackItem extends ErrorStackItem {
  timer: ReturnType<typeof setTimeout> | null
  remainingMs: number
  startedAt: number
}

function normalizeErrorMessage(raw: unknown): string {
  if (raw == null) return 'unknown error'
  const s = String(raw).trim()
  return s || 'unknown error'
}

export function useErrorStack(defaultTimeoutMs = 6000) {
  const items = ref<InternalErrorStackItem[]>([])

  const removeError = (id: string) => {
    const target = items.value.find((it) => it.id === id)
    if (target?.timer) clearTimeout(target.timer)
    items.value = items.value.filter((it) => it.id !== id)
  }

  const startTimer = (item: InternalErrorStackItem) => {
    if (item.timer) clearTimeout(item.timer)
    item.startedAt = Date.now()
    item.timer = setTimeout(() => removeError(item.id), item.remainingMs)
  }

  const pauseTimer = (id: string) => {
    const item = items.value.find((it) => it.id === id)
    if (!item || !item.timer) return
    clearTimeout(item.timer)
    item.timer = null
    const elapsed = Date.now() - item.startedAt
    item.remainingMs = Math.max(0, item.remainingMs - elapsed)
  }

  const resumeTimer = (id: string) => {
    const item = items.value.find((it) => it.id === id)
    if (!item || item.timer || item.remainingMs <= 0) return
    startTimer(item)
  }

  const pushError = (payload: { message: unknown; source: 'main' | 'assistant'; title?: string }) => {
    const item: InternalErrorStackItem = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      message: normalizeErrorMessage(payload.message),
      source: payload.source,
      title: payload.title ?? (payload.source === 'assistant' ? '助手错误' : '聊天错误'),
      createdAt: Date.now(),
      timeoutMs: defaultTimeoutMs,
      timer: null,
      remainingMs: defaultTimeoutMs,
      startedAt: Date.now(),
    }
    items.value.push(item)
    startTimer(item)
  }

  const clearAll = () => {
    for (const item of items.value) {
      if (item.timer) clearTimeout(item.timer)
    }
    items.value = []
  }

  return {
    items,
    pushError,
    removeError,
    pauseTimer,
    resumeTimer,
    clearAll,
  }
}
