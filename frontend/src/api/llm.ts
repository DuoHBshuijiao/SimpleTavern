/**
 * LLM 名录 / 协议自适应预览 / 模型能力 API（v0.810 T-820 / T-822 / T-824）
 *
 * - GET  /api/llm/catalog              内置厂商名录（pi 供应商 + models.dev/OpenRouter 元数据 + ST overlay）
 * - POST /api/llm/resolve-preview      「这次会怎么发」：协议 / 思考深度 clamp / Fast / 缓存计划，不打上游
 * - POST /api/llm/model-capabilities   模型能力（可用档位、Fast、成本）
 * - POST /api/llm/test-models          用请求内凭证列模型（支持 auto 协议 + providerId/providerParams）
 */
import { apiGet, apiPost } from './http'
import type { PromptCacheConfig } from '../types/models'

export interface LlmProviderPlaceholder {
  key: string
  label?: string
  example?: string
  hint?: string
}

export interface LlmCatalogProvider {
  id: string
  piId?: string | null
  label: string
  name: string
  region: string
  group: string
  baseUrlTemplate?: string | null
  placeholders: LlmProviderPlaceholder[]
  authStyle: string
  defaultProtocol: string
  supportedProtocols: string[]
  protocolVariant?: string | null
  protocolPaths: Record<string, string>
  cacheStrategy: string
  explicitCacheMarkers: boolean
  fastMode?: string | null
  docsUrl?: string | null
  keywords: string[]
  legacyIds: string[]
  requiresOAuth: boolean
  hint?: string | null
  envKeys: string[]
  unsupportedApis: string[]
  suggestedModels: string[]
}

export interface LlmCatalog {
  generatedAt?: string | null
  modelsGeneratedAt?: string | null
  source?: string | null
  providers: LlmCatalogProvider[]
}

export interface LlmModelCapabilities {
  modelId: string
  family: string
  providerId?: string | null
  name?: string | null
  reasoning: boolean
  efforts: string[]
  reasoningToggle: boolean
  temperature: boolean
  cost: Record<string, number>
  limit: Record<string, number>
  supportsFastMode: boolean
  fastModeCost?: Record<string, number> | null
  supportedParameters: string[]
  releaseDate?: string | null
  source: 'models_dev' | 'openrouter' | 'heuristic' | string
}

export interface ProtocolAdjustment {
  type: string
  from?: string | null
  to?: string | null
  reason?: string | null
  [key: string]: unknown
}

export interface PromptCachePlanMeta {
  mode: string
  ttl?: string | number | null
  breakpoints?: string[]
  minTokens?: number | null
  cacheKey?: string | null
}

/** 与后端 ProtocolResolution.to_public_dict 一致 */
export interface ProtocolResolution {
  requested: string
  effective: string
  effectiveLabel: string
  model: string
  family: string
  providerId?: string | null
  providerLabel?: string | null
  requestedEffort: string
  effort: string
  thinkingEnabled: boolean
  fastModeRequested: boolean
  fastMode: boolean
  availableEfforts: string[]
  supportsFastMode: boolean
  capabilitiesSource: string
  echoReasoning: boolean
  echoReasoningSource: string
  adjustments: ProtocolAdjustment[]
  reasons: string[]
  cache?: PromptCachePlanMeta | null
}

/** SSE done.usage / 非流式 usage：后端 Usage.to_public_dict */
export interface LlmUsage {
  inputTokens?: number | null
  outputTokens?: number | null
  totalTokens?: number | null
  cacheReadInputTokens?: number | null
  cacheWriteInputTokens?: number | null
  reasoningTokens?: number | null
  serviceTier?: string | null
  [key: string]: unknown
}

export interface ResolvePreviewRequest {
  baseUrl: string
  model: string
  protocol?: string | null
  providerId?: string | null
  providerParams?: Record<string, string> | null
  promptCache?: PromptCacheConfig | null
  reasoningEffort?: string | null
  fastMode?: boolean
  echoReasoning?: boolean
}

let catalogPromise: Promise<LlmCatalog> | null = null

/** 名录在一次会话内基本不变，做进程级缓存；force 时重新拉取 */
export function fetchLlmCatalog(force = false): Promise<LlmCatalog> {
  if (!catalogPromise || force) {
    catalogPromise = apiGet<LlmCatalog>('/api/llm/catalog').catch((err) => {
      catalogPromise = null
      throw err
    })
  }
  return catalogPromise
}

export function resolvePreview(body: ResolvePreviewRequest, signal?: AbortSignal): Promise<ProtocolResolution> {
  return apiPost<ProtocolResolution>('/api/llm/resolve-preview', body, signal)
}

export function fetchModelCapabilities(
  body: { model: string; providerId?: string | null; baseUrl?: string | null },
  signal?: AbortSignal,
): Promise<LlmModelCapabilities> {
  return apiPost<LlmModelCapabilities>('/api/llm/model-capabilities', body, signal)
}

export function testModels(
  body: {
    baseUrl: string
    apiKey: string
    protocol?: string | null
    providerId?: string | null
    providerParams?: Record<string, string> | null
    presetId?: string | null
    authStyle?: string | null
  },
  signal?: AbortSignal,
): Promise<string[]> {
  return apiPost<string[]>('/api/llm/test-models', body, signal)
}

export interface OAuthStatusPublic {
  loggedIn: boolean
  expiresAt?: number | null
  accountId?: string | null
  provider?: string | null
  enterpriseUrl?: string | null
  presetId?: string
}

export interface OAuthStartResult {
  sessionId: string
  method: 'device_code' | 'pkce'
  provider: string
  userCode?: string
  verificationUri?: string
  interval?: number
  expiresIn?: number
  authorizeUrl?: string
  redirectUri?: string
}

export interface OAuthPollResult extends OAuthStatusPublic {
  status: 'pending' | 'slow_down' | 'complete' | 'failed' | 'expired'
  message?: string
  intervalSeconds?: number
  presetId?: string
}

export function fetchOAuthStatus(presetId?: string): Promise<{ presets?: Record<string, OAuthStatusPublic> } & OAuthStatusPublic> {
  const q = presetId ? `?presetId=${encodeURIComponent(presetId)}` : ''
  return apiGet(`/api/llm/oauth/status${q}`)
}

export function startOAuthLogin(body: {
  presetId: string
  providerId?: string | null
  method?: 'device_code' | 'pkce'
  enterpriseUrl?: string | null
}): Promise<OAuthStartResult> {
  return apiPost('/api/llm/oauth/start', body)
}

export function pollOAuthLogin(sessionId: string): Promise<OAuthPollResult> {
  return apiPost('/api/llm/oauth/poll', { sessionId })
}

export function completeOAuthPkce(sessionId: string, callback: string): Promise<OAuthPollResult> {
  return apiPost('/api/llm/oauth/complete-pkce', { sessionId, callback })
}

export function cancelOAuthLogin(sessionId: string): Promise<{ ok: boolean }> {
  return apiPost('/api/llm/oauth/cancel', { sessionId })
}

export function logoutOAuthPreset(presetId: string): Promise<{ ok: boolean }> {
  return apiPost('/api/llm/oauth/logout', { presetId })
}

/** 与后端 Usage.to_public_dict 字段名保持一致；缺失时返回 null */
export function normalizeUsage(raw: unknown): LlmUsage | null {
  if (typeof raw !== 'object' || raw === null) return null
  const r = raw as Record<string, unknown>
  const num = (k: string): number | null => (typeof r[k] === 'number' ? (r[k] as number) : null)
  const out: LlmUsage = {
    inputTokens: num('inputTokens') ?? num('input_tokens'),
    outputTokens: num('outputTokens') ?? num('output_tokens'),
    totalTokens: num('totalTokens') ?? num('total_tokens'),
    cacheReadInputTokens: num('cacheReadInputTokens') ?? num('cache_read_input_tokens'),
    cacheWriteInputTokens: num('cacheWriteInputTokens') ?? num('cache_write_input_tokens'),
    reasoningTokens: num('reasoningTokens') ?? num('reasoning_tokens'),
    serviceTier:
      typeof r.serviceTier === 'string' ? r.serviceTier : typeof r.service_tier === 'string' ? (r.service_tier as string) : null,
  }
  const hasAny = Object.values(out).some((v) => v !== null && v !== undefined)
  return hasAny ? out : null
}
