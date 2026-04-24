/**
 * 出站 HTTP 请求日志查看 API 客户端
 *
 * 与后端 /api/http-log 对接：
 *  - getHttpLog 列表（最近 30 分钟元数据，从旧到新）
 *  - getHttpLogDetail 单条完整记录
 *  - clearHttpLog 手动清空
 */

import { apiDelete, apiGet } from './http'

export type HttpLogSource = 'llm' | 'update' | 'other'

export type HttpLogListItem = {
  id: string
  ts: string
  source: HttpLogSource
  method: string
  url: string
  responseStatus: number | null
  durationMs: number
  streaming: boolean
  error: string | null
}

export type HttpLogListResponse = {
  retentionMinutes: number
  count: number
  items: HttpLogListItem[]
}

export type HttpLogFilePlaceholder = {
  _kind: 'file'
  name: string | null
  mime: string | null
  bytes: number | null
  headPreview: string
  truncated: true
}

export type HttpLogDetail = HttpLogListItem & {
  tsMs: number
  requestHeaders: Record<string, string>
  requestBody: unknown
  responseHeaders: Record<string, string>
  responseBody: unknown
  extra?: Record<string, unknown>
}

export function getHttpLog(minutes?: number) {
  const qs = typeof minutes === 'number' ? `?minutes=${minutes}` : ''
  return apiGet<HttpLogListResponse>(`/api/http-log${qs}`)
}

export function getHttpLogDetail(id: string) {
  return apiGet<HttpLogDetail>(`/api/http-log/${encodeURIComponent(id)}`)
}

export function clearHttpLog() {
  return apiDelete('/api/http-log')
}
