import { apiGet, apiPut } from './http'

export type UsageScope = 'chat' | 'global'
export type UsageRange = 'all' | '7d' | '30d' | 'month'

export type UsageCostByCurrency = Record<
  string,
  { provider: number; estimated: number; total: number }
>

export type UsageSummaryMetrics = {
  requestCount: number
  completedCount: number
  failedCount: number
  cancelledCount: number
  inputTokens: number
  outputTokens: number
  avgInputTokens: number | null
  avgOutputTokens: number | null
  cacheReadInputTokens: number
  cacheWriteInputTokens: number
  cacheHitRate: number | null
  costByCurrency: UsageCostByCurrency
  unknownCostCount: number
  avgFirstTokenLatencyMs: number | null
  p50FirstTokenLatencyMs: number | null
  p95FirstTokenLatencyMs: number | null
  avgTotalDurationMs: number | null
  p50TotalDurationMs: number | null
  p95TotalDurationMs: number | null
}

export type UsageSummaryResponse = {
  ok: boolean
  scope: UsageScope
  chatId: string | null
  range: string
  eventCount: number
  summary: UsageSummaryMetrics
}

export type UsageModelRow = UsageSummaryMetrics & {
  provider: string | null
  protocol: string | null
  resolvedModel: string | null
}

export type UsageModelsResponse = {
  ok: boolean
  scope: UsageScope
  chatId: string | null
  range: string
  models: UsageModelRow[]
}

function usageQuery(params: {
  scope: UsageScope
  chatId?: string | null
  range?: UsageRange | string
}) {
  const q = new URLSearchParams()
  q.set('scope', params.scope)
  if (params.scope === 'chat' && params.chatId) q.set('chatId', params.chatId)
  if (params.range) q.set('range', params.range)
  return q.toString()
}

export function getUsageSummary(params: {
  scope: UsageScope
  chatId?: string | null
  range?: UsageRange | string
}) {
  return apiGet<UsageSummaryResponse>(`/api/usage/summary?${usageQuery(params)}`)
}

export function getUsageModels(params: {
  scope: UsageScope
  chatId?: string | null
  range?: UsageRange | string
}) {
  return apiGet<UsageModelsResponse>(`/api/usage/models?${usageQuery(params)}`)
}

export type PricingRule = {
  id: string
  provider?: string | null
  canonicalModelId?: string | null
  aliases?: string[]
  regexAliases?: string[]
  inputPerMillion?: number
  outputPerMillion?: number
  cacheReadPerMillion?: number
  cacheWritePerMillion?: number
  currency?: string
  source?: string
  readOnly?: boolean
  enabled?: boolean
}

export function getPricingRules() {
  return apiGet<{ ok: boolean; rules: PricingRule[]; catalogCount: number; userCount: number }>(
    '/api/pricing/rules',
  )
}

export function putPricingRule(id: string, body: Partial<PricingRule>) {
  return apiPut<{ ok: boolean; rule: PricingRule }>(`/api/pricing/rules/${encodeURIComponent(id)}`, body)
}
