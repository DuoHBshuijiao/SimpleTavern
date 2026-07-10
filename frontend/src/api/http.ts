/**
 * HTTP请求封装模块
 *
 * 提供统一的HTTP请求方法，封装fetch API，简化API调用。
 *
 * 主要功能：
 *    - GET请求：获取资源
 *    - PUT请求：更新资源
 *    - POST请求：创建资源或执行操作
 *    - DELETE请求：删除资源
 *
 * 主要函数：
 *    - apiGet: 发送GET请求
 *    - apiPut: 发送PUT请求
 *    - apiPost: 发送POST请求
 *    - apiDelete: 发送DELETE请求
 *
 * 文件关系：
 *    - 被导入：被stores、composables、components等模块导入用于API调用
 *    - 导入：无
 *    - 依赖：依赖浏览器fetch API
 *    - 位置：API层，提供HTTP请求的基础封装
 */

export interface AppErrorEnvelope {
  code: string
  message: string
  detail?: string | null
  source?: string
  retryable?: boolean
  requestId?: string
  provider?: string | null
  protocol?: string | null
  upstreamStatus?: number | null
  suggestedAction?: string | null
  terminal?: boolean
}

export class ApiError extends Error {
  readonly code: string
  readonly detail?: string | null
  readonly source?: string
  readonly retryable: boolean
  readonly requestId?: string
  readonly provider?: string | null
  readonly protocol?: string | null
  readonly upstreamStatus?: number | null
  readonly suggestedAction?: string | null
  readonly status?: number
  readonly terminal: boolean
  readonly rawBody?: string

  constructor(envelope: AppErrorEnvelope, options: { status?: number; rawBody?: string } = {}) {
    super(envelope.message)
    this.name = 'ApiError'
    this.code = envelope.code
    this.detail = envelope.detail
    this.source = envelope.source
    this.retryable = envelope.retryable ?? false
    this.requestId = envelope.requestId
    this.provider = envelope.provider
    this.protocol = envelope.protocol
    this.upstreamStatus = envelope.upstreamStatus
    this.suggestedAction = envelope.suggestedAction
    this.status = options.status
    this.terminal = envelope.terminal ?? false
    this.rawBody = options.rawBody
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function parseJsonText(value: string): unknown {
  const trimmed = value.trim()
  if (!trimmed) return value
  try {
    return JSON.parse(trimmed)
  } catch {
    return value
  }
}

function detailToMessage(detail: unknown): string | undefined {
  if (typeof detail === 'string' && detail.trim()) return detail.trim()
  if (Array.isArray(detail) && detail.length > 0) return '请求参数无效'
  if (isRecord(detail) && typeof detail.message === 'string' && detail.message.trim()) {
    return detail.message.trim()
  }
  return undefined
}

export function parseApiError(
  payload: unknown,
  options: {
    status?: number
    requestId?: string
    fallbackMessage?: string
    rawBody?: string
    terminal?: boolean
  } = {},
): ApiError {
  const parsed = typeof payload === 'string' ? parseJsonText(payload) : payload
  const root = isRecord(parsed) ? parsed : null
  const nestedError = root && isRecord(root.error) ? root.error : null
  const detailObject = root && isRecord(root.detail) ? root.detail : null
  const envelope = nestedError ?? detailObject ?? root

  const message =
    (envelope && typeof envelope.message === 'string' && envelope.message.trim()
      ? envelope.message.trim()
      : undefined) ??
    (root ? detailToMessage(root.detail) : undefined) ??
    (typeof parsed === 'string' && parsed.trim() ? parsed.trim() : undefined) ??
    options.fallbackMessage ??
    '请求失败'

  const detail =
    envelope && typeof envelope.detail === 'string'
      ? envelope.detail
      : root && typeof root.detail === 'string' && root.detail !== message
        ? root.detail
        : undefined
  const code =
    envelope && typeof envelope.code === 'string' && envelope.code.trim()
      ? envelope.code.trim()
      : options.status === 422
        ? 'request_validation_failed'
        : 'request_failed'

  return new ApiError(
    {
      code,
      message,
      detail,
      source: envelope && typeof envelope.source === 'string' ? envelope.source : undefined,
      retryable: envelope?.retryable === true,
      requestId:
        envelope && typeof envelope.requestId === 'string'
          ? envelope.requestId
          : options.requestId,
      provider: envelope && typeof envelope.provider === 'string' ? envelope.provider : undefined,
      protocol: envelope && typeof envelope.protocol === 'string' ? envelope.protocol : undefined,
      upstreamStatus:
        envelope && typeof envelope.upstreamStatus === 'number' ? envelope.upstreamStatus : undefined,
      suggestedAction:
        envelope && typeof envelope.suggestedAction === 'string' ? envelope.suggestedAction : undefined,
      terminal: envelope?.terminal === true || options.terminal === true,
    },
    { status: options.status, rawBody: options.rawBody },
  )
}

export async function responseToApiError(response: Response): Promise<ApiError> {
  const rawBody = await response.text()
  return parseApiError(rawBody, {
    status: response.status,
    requestId: response.headers.get('x-request-id') ?? undefined,
    fallbackMessage: response.statusText || `HTTP ${response.status}`,
    rawBody,
  })
}

async function assertOk(response: Response): Promise<void> {
  if (!response.ok) throw await responseToApiError(response)
}

/**
 * 发送GET请求
 *
 * 向指定路径发送GET请求，返回JSON格式的响应数据。
 *
 * @template T 响应数据的类型
 * @param {string} path - 请求路径
 * @returns {Promise<T>} 解析后的JSON响应数据
 * @throws {Error} 请求失败时抛出错误，错误信息为响应文本
 */
export async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  const r = await fetch(path, { method: 'GET', signal })
  await assertOk(r)
  return (await r.json()) as T
}

/**
 * 发送PUT请求
 *
 * 向指定路径发送PUT请求，更新资源。请求体会被序列化为JSON。
 *
 * @template T 响应数据的类型
 * @param {string} path - 请求路径
 * @param {unknown} body - 请求体数据，会被序列化为JSON
 * @returns {Promise<T>} 解析后的JSON响应数据
 * @throws {Error} 请求失败时抛出错误，错误信息为响应文本
 */
export async function apiPut<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const r = await fetch(path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })
  await assertOk(r)
  return (await r.json()) as T
}

/**
 * 发送POST请求
 *
 * 向指定路径发送POST请求，创建资源或执行操作。请求体会被序列化为JSON。
 *
 * @template T 响应数据的类型
 * @param {string} path - 请求路径
 * @param {unknown} body - 请求体数据，会被序列化为JSON
 * @returns {Promise<T>} 解析后的JSON响应数据
 * @throws {Error} 请求失败时抛出错误，错误信息为响应文本
 */
export async function apiPost<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const r = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })
  await assertOk(r)
  return (await r.json()) as T
}

/**
 * 发送 multipart/form-data POST 请求
 */
export async function apiPostFormData<T>(path: string, body: FormData, signal?: AbortSignal): Promise<T> {
  const r = await fetch(path, {
    method: 'POST',
    body,
    signal,
  })
  await assertOk(r)
  return (await r.json()) as T
}

/**
 * 发送DELETE请求
 *
 * 向指定路径发送DELETE请求，删除资源。
 *
 * @param {string} path - 请求路径
 * @returns {Promise<void>} 请求成功时返回void
 * @throws {Error} 请求失败时抛出错误，错误信息为响应文本
 */
export async function apiDelete(path: string): Promise<void> {
  const r = await fetch(path, { method: 'DELETE' })
  await assertOk(r)
}


