/**
 * SSE（Server-Sent Events）流式传输处理模块
 *
 * 提供Server-Sent Events流式数据的接收和处理功能，用于实时接收服务器推送的数据流。
 *
 * 主要功能：
 *    - 解析SSE事件块：解析SSE格式的事件数据
 *    - 查找事件分隔符：识别SSE事件之间的分隔符（支持LF和CRLF）
 *    - 消费SSE流：发送POST请求并实时处理返回的SSE事件流
 *
 * 主要函数：
 *    - parseEventBlock: 解析SSE事件块
 *    - findSseSeparatorIndex: 查找SSE事件分隔符位置
 *    - postAndConsumeSse: 发送POST请求并消费SSE流
 *
 * 实现原理：
 *    - 使用ReadableStream API读取响应流
 *    - 按SSE协议格式解析事件（event:和data:字段）
 *    - 每处理20个事件后让出主线程，避免UI阻塞
 *    - 支持AbortSignal取消请求
 *
 * 文件关系：
 *    - 被导入：被composables、views等模块导入用于流式数据传输
 *    - 导入：无
 *    - 依赖：依赖浏览器fetch API和ReadableStream API
 *    - 位置：API层，提供SSE流式传输的基础封装
 */

import { parseApiError, responseToApiError } from './http'

/**
 * SSE事件类型
 *
 * 表示一个SSE事件，包含事件类型和数据。
 */
export type SseEvent = { event: string; data: unknown }

/**
 * 解析SSE事件块
 *
 * 解析SSE格式的事件块字符串，提取event和data字段。
 * 支持多行data字段（使用换行符连接）。
 * 尝试将data解析为JSON，失败则作为字符串返回。
 *
 * @param {string} block - SSE事件块字符串
 * @returns {SseEvent | null} 解析后的事件对象，如果无有效数据则返回null
 */
function parseEventBlock(block: string): SseEvent | null {
  const lines = block.split('\n').map((l) => l.trimEnd())
  let event = 'message'
  const dataLines: string[] = []
  for (const line of lines) {
    if (!line) continue
    if (line.startsWith('event:')) {
      event = line.slice('event:'.length).trim()
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice('data:'.length).trim())
    }
  }
  if (!dataLines.length) return null
  const dataStr = dataLines.join('\n')
  try {
    return { event, data: JSON.parse(dataStr) }
  } catch {
    return { event, data: dataStr }
  }
}

/**
 * 查找SSE事件分隔符位置
 *
 * SSE事件之间使用双换行符（\n\n或\r\n\r\n）分隔。
 * 查找缓冲区中第一个分隔符的位置和长度。
 *
 * @param {string} buffer - 待查找的缓冲区字符串
 * @returns {{ idx: number; sepLen: number } | null} 分隔符位置和长度，如果未找到则返回null
 */
function findSseSeparatorIndex(buffer: string): { idx: number; sepLen: number } | null {
  const idxLf = buffer.indexOf('\n\n')
  const idxCrLf = buffer.indexOf('\r\n\r\n')
  if (idxLf < 0 && idxCrLf < 0) return null
  if (idxLf >= 0 && idxCrLf >= 0) {
    return idxLf <= idxCrLf ? { idx: idxLf, sepLen: 2 } : { idx: idxCrLf, sepLen: 4 }
  }
  if (idxLf >= 0) return { idx: idxLf, sepLen: 2 }
  return { idx: idxCrLf, sepLen: 4 }
}

/**
 * 发送POST请求并消费SSE流
 *
 * 向指定路径发送POST请求，接收Server-Sent Events流式响应。
 * 实时解析并处理每个SSE事件，通过回调函数通知调用者。
 * 每处理20个事件后让出主线程，避免UI阻塞。
 *
 * @param {string} path - 请求路径
 * @param {unknown} body - 请求体数据，会被序列化为JSON
 * @param {(evt: SseEvent) => void} onEvent - 事件回调函数，每个SSE事件触发一次
 * @param {AbortSignal} [signal] - 可选的AbortSignal，用于取消请求
 * @returns {Promise<void>} 流处理完成时返回
 * @throws {Error} 请求失败时抛出错误，错误信息为响应文本
 */
export async function postAndConsumeSse(
  path: string,
  body: unknown,
  onEvent: (evt: SseEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const r = await fetch(path, {
    method: 'POST',
    headers: {
      Accept: 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
    signal,
  })
  if (!r.ok) throw await responseToApiError(r)
  if (!r.body) return

  const reader = r.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let processedEventsSinceYield = 0

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    while (true) {
      const sep = findSseSeparatorIndex(buffer)
      if (!sep) break
      const chunk = buffer.slice(0, sep.idx)
      buffer = buffer.slice(sep.idx + sep.sepLen)
      const evt = parseEventBlock(chunk)
      if (evt) {
        onEvent(evt)
        if (evt.event === 'error') {
          const terminalError = parseApiError(evt.data, {
            requestId: r.headers.get('x-request-id') ?? undefined,
            fallbackMessage: '流式请求失败',
            terminal: true,
          })
          try {
            await reader.cancel()
          } catch {
            // 终止错误已确定；取消 reader 的附带失败不覆盖主错误。
          }
          throw terminalError
        }
        processedEventsSinceYield += 1
        // 让出主线程给渲染：避免某些代理/缓冲导致一次性读到大量 SSE 时 UI “憋到最后才更新”
        if (processedEventsSinceYield >= 20) {
          processedEventsSinceYield = 0
          await new Promise<void>((resolve) => setTimeout(resolve, 0))
        }
      }
    }
  }
}


