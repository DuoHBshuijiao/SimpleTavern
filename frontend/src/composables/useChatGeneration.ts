/**
 * useChatGeneration - 主聊天生成 SSE 消费（T-812）
 *
 * ChatPage 保留发送/群聊/插话/重写的页面编排；本 composable 统一：
 * - abort / 停止标志
 * - meta / usage / reasoning / delta / done / error
 * - 把 usage 与 generationMetadata 补丁到本地消息
 * - 停止或失败时选择 persist 而非丢弃本地流式内容
 */
import { ref, type Ref } from 'vue'
import type { SseEvent } from '../api/sse'
import type { ChatMessage } from '../types/models'
import type { UseStreamOutput } from './useStreamOutput'

export type ChatGenerationDeps = {
  chats: {
    patchLocalMessage: (messageId: string, patch: Partial<ChatMessage>) => void
    getLocalMessage?: (messageId: string) => ChatMessage | undefined
  }
  stream: UseStreamOutput
  onAssistantContentDeltaStarted: () => void
  chatReasoningContent: Ref<string>
  chatReasoningMessageId: Ref<string | null>
  chatReasoningStreamActive: Ref<boolean>
  pushCurrentReasoningToBlocks: (serverId?: string, localId?: string) => void
  clearReasoningPhaseTiming: () => void
}

export type GenerateDonePayload = {
  assistantMessageId?: string
  usage?: ChatMessage['usage']
  generationMetadata?: ChatMessage['generationMetadata']
  [key: string]: unknown
}

export function useChatGeneration(deps: ChatGenerationDeps) {
  const aborter = ref<AbortController | null>(null)
  const stopRequested = ref(false)
  const stopStreamingHold = ref(false)

  function beginGenerateAbort() {
    aborter.value?.abort()
    aborter.value = new AbortController()
    stopRequested.value = false
    stopStreamingHold.value = false
    return aborter.value.signal
  }

  function shouldIgnoreStreamingEventWhileStopping(eventName: string): boolean {
    return stopRequested.value && eventName === 'delta'
  }

  function applyGenerateDonePayload(localAssistantId: string, data: unknown) {
    if (!data || typeof data !== 'object') return
    const payload = data as GenerateDonePayload
    const patch: Partial<ChatMessage> = {}
    if (payload.usage && typeof payload.usage === 'object') {
      patch.usage = payload.usage
    }
    if (payload.generationMetadata && typeof payload.generationMetadata === 'object') {
      const existing = (deps.chats.getLocalMessage?.(localAssistantId)?.generationMetadata || {}) as Record<string, unknown>
      patch.generationMetadata = {
        ...existing,
        ...(payload.generationMetadata as Record<string, unknown>),
      } as ChatMessage['generationMetadata']
    }
    if (Object.keys(patch).length) {
      deps.chats.patchLocalMessage(localAssistantId, patch)
    }
  }

  function applyMetaPayload(localAssistantId: string, data: unknown) {
    if (!data || typeof data !== 'object') return
    const meta = data as Record<string, unknown>
    const existing = (deps.chats.getLocalMessage?.(localAssistantId)?.generationMetadata || {}) as Record<string, unknown>
    const next: Record<string, unknown> = { ...existing }
    for (const key of [
      'requestId',
      'provider',
      'protocol',
      'resolvedModel',
      'protocolResolution',
      'cache',
      'warnings',
    ] as const) {
      if (meta[key] !== undefined) next[key] = meta[key]
    }
    deps.chats.patchLocalMessage(localAssistantId, {
      generationMetadata: next as ChatMessage['generationMetadata'],
    })
  }

  function makeGenerateSseHandler(options: {
    localAssistantId: string
    onTerminalError?: (data: unknown) => void
  }) {
    const { localAssistantId, onTerminalError } = options
    return (evt: SseEvent) => {
      if (shouldIgnoreStreamingEventWhileStopping(evt.event)) return
      if (evt.event === 'delta') deps.onAssistantContentDeltaStarted()
      if (evt.event === 'meta') {
        applyMetaPayload(localAssistantId, evt.data)
        return
      }
      if (evt.event === 'usage') {
        if (evt.data && typeof evt.data === 'object') {
          deps.chats.patchLocalMessage(localAssistantId, {
            usage: evt.data as ChatMessage['usage'],
          })
        }
        return
      }
      if (evt.event === 'delta') {
        const data = evt.data as { text?: string } | undefined
        const t = data?.text
        if (typeof t === 'string') {
          deps.stream.appendDeltaBuffered(localAssistantId, t)
        }
        return
      }
      if (evt.event === 'reasoning') {
        const data = evt.data as { text?: string } | undefined
        const t = data?.text
        if (typeof t === 'string') {
          deps.chatReasoningContent.value += t
        }
        return
      }
      if (evt.event === 'done') {
        const data = evt.data as GenerateDonePayload | undefined
        const serverId = data?.assistantMessageId
        if (serverId && deps.chatReasoningContent.value) {
          deps.chatReasoningMessageId.value = serverId
        }
        deps.pushCurrentReasoningToBlocks(serverId ?? undefined, localAssistantId)
        applyGenerateDonePayload(localAssistantId, data)
        return
      }
      if (evt.event === 'error') {
        deps.chatReasoningStreamActive.value = false
        deps.clearReasoningPhaseTiming()
        onTerminalError?.(evt.data)
      }
    }
  }

  function consumeGenerationFinallyFlags(hadError: boolean): 'persist' | 'reload' {
    if (stopStreamingHold.value || hadError) {
      stopStreamingHold.value = false
      return 'persist'
    }
    return 'reload'
  }

  return {
    aborter,
    stopRequested,
    stopStreamingHold,
    beginGenerateAbort,
    shouldIgnoreStreamingEventWhileStopping,
    applyGenerateDonePayload,
    makeGenerateSseHandler,
    consumeGenerationFinallyFlags,
  }
}

export type UseChatGeneration = ReturnType<typeof useChatGeneration>
