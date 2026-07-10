/**
 * 主聊天 / 助手流式错误栈（右下角 ErrorModal）。
 * 与 useNotify 分工：非阻塞业务提示、确认框走全局 AppNotificationHost，本栈保留自动消失与复制。
 */
import { ref } from 'vue'
import { ApiError } from '../api/http'

export interface ErrorStackItem {
  id: string
  message: string
  source: 'main' | 'assistant'
  title: string
  createdAt: number
  timeoutMs: number
  code?: string
  suggestedAction?: string
  requestId?: string
}

interface InternalErrorStackItem extends ErrorStackItem {
  timer: ReturnType<typeof setTimeout> | null
  remainingMs: number
  startedAt: number
}

export interface ErrorStackPushPayload {
  message: unknown
  source: 'main' | 'assistant'
  title?: string
  code?: string
  suggestedAction?: string
  requestId?: string
}

function normalizeError(raw: unknown): {
  message: string
  code?: string
  suggestedAction?: string
  requestId?: string
} {
  if (raw instanceof ApiError) {
    return {
      message: raw.message || 'unknown error',
      code: raw.code,
      suggestedAction: raw.suggestedAction ?? undefined,
      requestId: raw.requestId,
    }
  }
  if (raw instanceof Error) {
    return { message: raw.message.trim() || 'unknown error' }
  }
  if (typeof raw === 'object' && raw !== null) {
    const value = raw as Record<string, unknown>
    const message = typeof value.message === 'string' ? value.message.trim() : ''
    return {
      message: message || 'unknown error',
      code: typeof value.code === 'string' ? value.code : undefined,
      suggestedAction: typeof value.suggestedAction === 'string' ? value.suggestedAction : undefined,
      requestId: typeof value.requestId === 'string' ? value.requestId : undefined,
    }
  }
  if (raw == null) return { message: 'unknown error' }
  const message = String(raw).trim()
  return { message: message || 'unknown error' }
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

  const pushError = (payload: ErrorStackPushPayload) => {
    const normalized = normalizeError(payload.message)
    const item: InternalErrorStackItem = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      message: normalized.message,
      source: payload.source,
      title: payload.title ?? (payload.source === 'assistant' ? '助手错误' : '聊天错误'),
      createdAt: Date.now(),
      timeoutMs: defaultTimeoutMs,
      code: payload.code ?? normalized.code,
      suggestedAction: payload.suggestedAction ?? normalized.suggestedAction,
      requestId: payload.requestId ?? normalized.requestId,
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
