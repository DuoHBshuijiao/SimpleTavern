/**
 * useStreamOutput - 流式输出处理逻辑
 * 
 * 负责处理 LLM 流式响应的缓冲、分块动画和 DOM 操作
 */
import { reactive, nextTick } from 'vue'

export interface StreamOutputOptions {
  chunkSize?: number
  animDuration?: number
}

export interface StreamOutputState {
  bufferMap: Map<string, string>
  pendingChunks: Map<string, { id: string; text: string }[]>
  committedMap: Map<string, string>
  activeMessageIds: Set<string>
}

export function useStreamOutput(
  chatsStore: {
    appendLocalMessageContent: (messageId: string, content: string) => void
  },
  scrollToBottom: () => void,
  options: StreamOutputOptions = {}
) {
  const CHUNK_SIZE = options.chunkSize ?? 12
  const ANIM_DURATION = options.animDuration ?? 350

  // 响应式状态
  const bufferMap = reactive(new Map<string, string>())
  const pendingChunks = reactive(new Map<string, { id: string; text: string }[]>())
  const committedMap = reactive(new Map<string, string>())
  const activeMessageIds = reactive(new Set<string>())

  // 非响应式状态（内部使用）
  const chunkTimers = new Map<string, number>()
  const messageContentRefs = new Map<string, HTMLElement>()
  const pendingElements = new Map<string, Map<string, HTMLElement>>()
  const committedElements = new Map<string, Map<string, HTMLElement>>()
  let chunkSeq = 0

  /**
   * 注册一个消息 ID 为流式消息
   */
  function registerStreamMessage(messageId: string) {
    activeMessageIds.add(messageId)
  }

  /**
   * 设置消息内容的 DOM 引用
   */
  function setMessageContentRef(messageId: string, el: HTMLElement | null) {
    if (!el) {
      messageContentRefs.delete(messageId)
      pendingElements.delete(messageId)
      return
    }
    messageContentRefs.set(messageId, el)
  }

  /**
   * 追加流式增量内容（带缓冲）
   */
  function appendDeltaBuffered(messageId: string, delta: string) {
    const current = bufferMap.get(messageId) ?? ''
    const combined = current + delta
    if (combined.length < CHUNK_SIZE) {
      bufferMap.set(messageId, combined)
      return
    }
    const flushCount = Math.floor(combined.length / CHUNK_SIZE) * CHUNK_SIZE
    const toFlush = combined.slice(0, flushCount)
    const remaining = combined.slice(flushCount)
    bufferMap.set(messageId, remaining)
    for (let i = 0; i < toFlush.length; i += CHUNK_SIZE) {
      scheduleChunk(messageId, toFlush.slice(i, i + CHUNK_SIZE))
    }
  }

  /**
   * 调度一个文本块的动画
   */
  function scheduleChunk(messageId: string, chunk: string) {
    if (!chunk) return
    const entry = { id: `${messageId}_${Date.now()}_${chunkSeq++}`, text: chunk }
    const list = pendingChunks.get(messageId) ?? []
    list.push(entry)
    pendingChunks.set(messageId, list)
    appendChunkToDom(messageId, entry)
    const timer = window.setTimeout(() => finalizeChunk(messageId, entry.id), ANIM_DURATION)
    chunkTimers.set(entry.id, timer)
  }

  /**
   * 将文本块追加到 DOM
   */
  function appendChunkToDom(messageId: string, entry: { id: string; text: string }) {
    nextTick(() => {
      const root = messageContentRefs.get(messageId)
      if (!root) return
      const markdownEl = root.querySelector('.stream-markdown') as HTMLElement | null
      if (!markdownEl) return
      const paragraph = markdownEl.querySelector('p:last-child') as HTMLElement | null
      const target = paragraph ?? markdownEl
      const span = document.createElement('span')
      span.className = 'stream-append'
      span.textContent = entry.text
      target.appendChild(span)
      const elementMap = pendingElements.get(messageId) ?? new Map<string, HTMLElement>()
      elementMap.set(entry.id, span)
      pendingElements.set(messageId, elementMap)
    })
  }

  /**
   * 将块元素移动到已提交状态
   */
  function moveChunkToCommitted(messageId: string, chunkId: string) {
    const pendingMap = pendingElements.get(messageId)
    if (!pendingMap) return
    const el = pendingMap.get(chunkId)
    if (el) {
      el.classList.add('stream-append--done')
    }
    pendingMap.delete(chunkId)
    if (pendingMap.size === 0) {
      pendingElements.delete(messageId)
    }
    if (!el) return
    const committedMap = committedElements.get(messageId) ?? new Map<string, HTMLElement>()
    committedMap.set(chunkId, el)
    committedElements.set(messageId, committedMap)
  }

  /**
   * 清理块元素
   */
  function clearChunkElements(map: Map<string, Map<string, HTMLElement>>, messageId: string) {
    const elementMap = map.get(messageId)
    if (!elementMap) return
    for (const el of elementMap.values()) {
      if (el?.parentNode) el.parentNode.removeChild(el)
    }
    map.delete(messageId)
  }

  /**
   * 追加已提交的文本到消息内容
   */
  function appendCommittedText(messageId: string, text: string) {
    if (!text) return
    chatsStore.appendLocalMessageContent(messageId, text)
    scrollToBottom()
  }

  /**
   * 完成一个文本块的处理
   */
  function finalizeChunk(messageId: string, chunkId: string) {
    const list = pendingChunks.get(messageId)
    if (!list || list.length === 0) return
    const idx = list.findIndex((c) => c.id === chunkId)
    if (idx < 0) return
    const [chunk] = list.splice(idx, 1)
    pendingChunks.set(messageId, list)
    const timer = chunkTimers.get(chunkId)
    if (timer) {
      clearTimeout(timer)
      chunkTimers.delete(chunkId)
    }
    if (chunk?.text) {
      const committed = committedMap.get(messageId) ?? ''
      committedMap.set(messageId, committed + chunk.text)
    }
    moveChunkToCommitted(messageId, chunkId)
    if (list.length === 0) {
      pendingChunks.delete(messageId)
      const committedText = committedMap.get(messageId) ?? ''
      committedMap.delete(messageId)
      clearChunkElements(committedElements, messageId)
      appendCommittedText(messageId, committedText)
    }
  }

  /**
   * 刷新指定消息的所有流式缓冲
   */
  function flushForMessage(messageId: string) {
    const list = pendingChunks.get(messageId)
    const committedText = committedMap.get(messageId) ?? ''
    if (list && list.length > 0) {
      for (const entry of list) {
        const timer = chunkTimers.get(entry.id)
        if (timer) {
          clearTimeout(timer)
          chunkTimers.delete(entry.id)
        }
      }
      clearChunkElements(pendingElements, messageId)
      pendingChunks.delete(messageId)
    }
    clearChunkElements(committedElements, messageId)
    committedMap.delete(messageId)
    const remaining = bufferMap.get(messageId)
    const pendingText = list && list.length > 0 ? list.map((c) => c.text).join('') : ''
    appendCommittedText(messageId, committedText + pendingText)
    if (remaining && remaining.length > 0) {
      chatsStore.appendLocalMessageContent(messageId, remaining)
    }
    bufferMap.delete(messageId)
    activeMessageIds.delete(messageId)
    scrollToBottom()
  }

  /**
   * 刷新所有活跃的流式消息
   */
  function flushAll() {
    const ids = Array.from(activeMessageIds)
    for (const id of ids) {
      flushForMessage(id)
    }
  }

  /**
   * 清理所有状态
   */
  function cleanup() {
    flushAll()
    bufferMap.clear()
    pendingChunks.clear()
    committedMap.clear()
    activeMessageIds.clear()
    chunkTimers.clear()
    messageContentRefs.clear()
    pendingElements.clear()
    committedElements.clear()
  }

  return {
    // 状态
    bufferMap,
    pendingChunks,
    committedMap,
    activeMessageIds,
    
    // 方法
    registerStreamMessage,
    setMessageContentRef,
    appendDeltaBuffered,
    flushForMessage,
    flushAll,
    cleanup,
  }
}

export type UseStreamOutput = ReturnType<typeof useStreamOutput>
