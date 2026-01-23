/**
 * useStreamOutput - 流式输出处理Composable
 *
 * 负责处理LLM流式响应的缓冲、分块动画和DOM操作，实现打字机效果。
 *
 * 主要功能：
 *    - 缓冲流式数据：将接收到的增量数据缓冲，按块处理
 *    - 分块动画：将文本块添加到DOM并应用动画效果
 *    - 状态管理：管理待处理块、已提交块等状态
 *    - DOM操作：直接操作消息内容的DOM元素
 *
 * 主要函数：
 *    - registerStreamMessage: 注册流式消息
 *    - setMessageContentRef: 设置消息DOM引用
 *    - appendDeltaBuffered: 追加缓冲的增量内容
 *    - flushForMessage: 刷新指定消息的缓冲
 *    - flushAll: 刷新所有消息的缓冲
 *    - cleanup: 清理所有状态
 *
 * 实现原理：
 *    - 使用缓冲机制，将接收到的增量数据累积到一定大小后再处理
 *    - 将文本块添加到DOM，应用CSS动画类，实现打字机效果
 *    - 使用定时器控制动画时长，动画结束后将内容提交到Store
 *    - 支持多个消息同时进行流式输出
 *
 * 文件关系：
 *    - 被导入：被composables/index.ts导出，被views/ChatPage.vue使用
 *    - 导入：导入vue的reactive和nextTick
 *    - 依赖：依赖stores/chats.ts的appendLocalMessageContent方法
 *    - 位置：Composables层，提供流式输出处理逻辑
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
   * 注册一个消息ID为流式消息
   *
   * 将消息ID添加到活跃消息集合中，标记该消息正在进行流式输出。
   *
   * @param {string} messageId - 消息ID
   */
  function registerStreamMessage(messageId: string) {
    activeMessageIds.add(messageId)
  }

  /**
   * 设置消息内容的DOM引用
   *
   * 保存消息内容容器的DOM元素引用，用于后续的DOM操作。
   * 如果传入null，则清除该消息的引用和相关元素。
   *
   * @param {string} messageId - 消息ID
   * @param {HTMLElement | null} el - DOM元素引用，null表示清除
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
   *
   * 将接收到的增量内容添加到缓冲区。
   * 当缓冲区累积到CHUNK_SIZE大小时，将完整的块调度处理。
   * 剩余不足一个块大小的内容保留在缓冲区中。
   *
   * @param {string} messageId - 消息ID
   * @param {string} delta - 增量内容
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
   *
   * 创建一个文本块条目，添加到待处理列表，并立即添加到DOM。
   * 设置定时器，在ANIM_DURATION后完成该块的处理。
   *
   * @param {string} messageId - 消息ID
   * @param {string} chunk - 文本块内容
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
   * 将文本块追加到DOM
   *
   * 在消息内容的markdown容器中，找到最后一个段落或容器本身，
   * 创建一个span元素，添加stream-append类，并追加到目标元素。
   * 使用nextTick确保DOM已更新。
   *
   * @param {string} messageId - 消息ID
   * @param {{ id: string; text: string }} entry - 文本块条目
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
   *
   * 将待处理元素移动到已提交元素映射中，并添加stream-append--done类。
   * 从待处理映射中删除该元素。
   *
   * @param {string} messageId - 消息ID
   * @param {string} chunkId - 文本块ID
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
   *
   * 从DOM中移除指定消息的所有块元素，并从映射中删除。
   *
   * @param {Map<string, Map<string, HTMLElement>>} map - 元素映射
   * @param {string} messageId - 消息ID
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
   *
   * 将已完成的文本块内容追加到Store中的消息内容。
   * 调用chatsStore.appendLocalMessageContent（来自stores/chats.ts）更新状态。
   * 然后滚动到底部。
   *
   * @param {string} messageId - 消息ID
   * @param {string} text - 要追加的文本
   */
  function appendCommittedText(messageId: string, text: string) {
    if (!text) return
    chatsStore.appendLocalMessageContent(messageId, text)
    scrollToBottom()
  }

  /**
   * 完成一个文本块的处理
   *
   * 当定时器触发时调用，表示一个文本块的动画已完成。
   * 将块从待处理列表移除，添加到已提交文本中，并移动到已提交状态。
   * 如果所有块都处理完成，则将已提交文本追加到Store并清理DOM元素。
   *
   * @param {string} messageId - 消息ID
   * @param {string} chunkId - 文本块ID
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
   *
   * 立即完成指定消息的所有待处理块，将所有缓冲内容追加到Store。
   * 清理所有相关的DOM元素和状态。
   * 用于流式传输结束或取消时。
   *
   * @param {string} messageId - 消息ID
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
   *
   * 遍历所有活跃的消息ID，对每个消息调用flushForMessage。
   * 用于批量刷新所有流式输出。
   */
  function flushAll() {
    const ids = Array.from(activeMessageIds)
    for (const id of ids) {
      flushForMessage(id)
    }
  }

  /**
   * 清理所有状态
   *
   * 刷新所有消息，然后清空所有状态映射和集合。
   * 用于组件卸载或重置时。
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
