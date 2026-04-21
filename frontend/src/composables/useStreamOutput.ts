/**
 * useStreamOutput - 流式输出缓冲 Composable
 *
 * 职责（重构后）：
 *    - 单源：只负责把 SSE delta 合并写入 store（`appendLocalMessageContent`），
 *      不再自己操作 DOM；视觉上的打字机淡入效果由 MessageList 在渲染后包裹末尾新字完成。
 *    - rAF 合并：同一帧内多条 delta 合并成一次 store 更新，降低 v-html 重渲染频次与高度抖动。
 *
 * 主要函数：
 *    - registerStreamMessage: 注册流式消息
 *    - appendDeltaBuffered: 追加增量内容（rAF 合并）
 *    - flushForMessage: 同步刷新指定消息的缓冲并写入 store
 *    - flushAll: 刷新所有活跃流式消息
 *    - cleanup: 清理全部状态
 *
 * 文件关系：
 *    - 被导入：被 composables/index.ts 导出，被 views/ChatPage.vue 使用
 *    - 依赖：依赖 stores/chats.ts 的 appendLocalMessageContent 方法
 *    - 位置：Composables 层，提供流式内容写入协调
 */
import { reactive } from 'vue'

export interface StreamOutputOptions {
  /** 保留字段以兼容旧调用点（当前实现不再分块动画） */
  chunkSize?: number
  /** 保留字段以兼容旧调用点 */
  animDuration?: number
}

export interface StreamOutputState {
  bufferMap: Map<string, string>
  activeMessageIds: Set<string>
}

export function useStreamOutput(
  chatsStore: {
    appendLocalMessageContent: (messageId: string, content: string) => void
  },
  scrollToBottom: () => void,
  _options: StreamOutputOptions = {}
) {
  const bufferMap = reactive(new Map<string, string>())
  const activeMessageIds = reactive(new Set<string>())

  /** 每个消息最多挂一个 rAF；写入一次后清除 */
  const rafIds = new Map<string, number>()

  /**
   * 注册流式消息
   *
   * 标记该 messageId 正处于流式输出阶段。
   */
  function registerStreamMessage(messageId: string) {
    activeMessageIds.add(messageId)
  }

  /**
   * 同帧内把该消息已累积的缓冲一次性写入 store。
   * 同一时刻对同一个 id 只会有一个挂起的 rAF。
   */
  function scheduleFlush(messageId: string) {
    if (rafIds.has(messageId)) return
    const id = requestAnimationFrame(() => {
      rafIds.delete(messageId)
      const buffered = bufferMap.get(messageId)
      if (!buffered) return
      bufferMap.set(messageId, '')
      chatsStore.appendLocalMessageContent(messageId, buffered)
      scrollToBottom()
    })
    rafIds.set(messageId, id)
  }

  /**
   * 追加流式增量内容（rAF 合并）
   *
   * 把 delta 累加到缓冲；下一帧统一 flush 到 store。这样 SSE 高频 delta 不会触发
   * 每条一次的 v-html 重渲染，减轻复杂 Markdown 场景的高度跳变。
   *
   * @param {string} messageId - 消息ID
   * @param {string} delta - 增量内容
   */
  function appendDeltaBuffered(messageId: string, delta: string) {
    if (!delta) return
    const current = bufferMap.get(messageId) ?? ''
    bufferMap.set(messageId, current + delta)
    scheduleFlush(messageId)
  }

  /**
   * 立即刷新指定消息的缓冲
   *
   * 用于流式结束或取消时：把剩余缓冲同步写入 store，取消挂起的 rAF。
   *
   * @param {string} messageId - 消息ID
   */
  function flushForMessage(messageId: string) {
    const pendingRaf = rafIds.get(messageId)
    if (pendingRaf != null) {
      cancelAnimationFrame(pendingRaf)
      rafIds.delete(messageId)
    }
    const buffered = bufferMap.get(messageId)
    if (buffered && buffered.length > 0) {
      chatsStore.appendLocalMessageContent(messageId, buffered)
    }
    bufferMap.delete(messageId)
    activeMessageIds.delete(messageId)
    scrollToBottom()
  }

  /**
   * 刷新全部活跃流式消息
   */
  function flushAll() {
    const ids = Array.from(activeMessageIds)
    for (const id of ids) {
      flushForMessage(id)
    }
  }

  /**
   * 清理所有状态（组件卸载时调用）
   */
  function cleanup() {
    flushAll()
    for (const id of rafIds.values()) cancelAnimationFrame(id)
    rafIds.clear()
    bufferMap.clear()
    activeMessageIds.clear()
  }

  return {
    bufferMap,
    activeMessageIds,

    registerStreamMessage,
    appendDeltaBuffered,
    flushForMessage,
    flushAll,
    cleanup,
  }
}

export type UseStreamOutput = ReturnType<typeof useStreamOutput>
