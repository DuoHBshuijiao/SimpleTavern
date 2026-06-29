<script setup lang="ts">
/**
 * HttpRecordPreview - HTTP 请求记录的 Pretty 预览
 *
 * 与聊天气泡刻意区分：方形左边条卡片、全部左对齐、低饱和背景。
 * 按身份分层：
 *  - SYSTEM / USER / ASSISTANT：LLM 请求的 messages 解析
 *  - PROGRAM：非 LLM 的出站请求（GitHub 等）或无 messages 的 llm 请求
 *  - RESPONSE：响应正文（assistant.content / 错误 / 普通响应）
 *  - TOOL：底部工具区（tools 声明、tool_calls、role=tool 消息）
 *
 * 约束：
 *  - 不渲染 markdown，正文走 <pre whitespace-pre-wrap>
 *  - 图像原样渲染（限宽 220px / 限高 160px）
 *  - 文件内容以 { _kind:'file', ... headPreview } 的 placeholder 展示
 */
import { computed } from 'vue'
import { FileText, Image as ImageIcon, Wrench } from 'lucide-vue-next'
import CodeViewer from '../common/CodeViewer.vue'
import type { HttpLogDetail } from '../../api/httpLog'

const props = defineProps<{
  record: HttpLogDetail
}>()

type Role = 'system' | 'user' | 'assistant' | 'program' | 'response' | 'tool'

type FilePlaceholder = {
  _kind: 'file'
  name?: string | null
  mime?: string | null
  bytes?: number | null
  headPreview?: string
  truncated?: boolean
}

type ContentPart =
  | { kind: 'text'; text: string }
  | { kind: 'image'; url: string; mime?: string | null; bytesHint?: number | null }
  | { kind: 'file'; placeholder: FilePlaceholder }
  | { kind: 'unknown'; json: unknown }

type MessageCard = {
  role: Role
  label: string
  name?: string | null
  parts: ContentPart[]
  tool_call_id?: string | null
  /** 对应 assistant 的工具调用（放到底部工具区，不出现在 parts 里） */
}

type ToolDef = {
  name: string
  description?: string | null
  parameters?: unknown
}

type ToolCallCard = {
  id?: string
  name: string
  argumentsRaw: string
  argumentsParsed?: unknown
}

type ToolReturnCard = {
  name?: string | null
  tool_call_id?: string | null
  parts: ContentPart[]
}

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v)
}

function isFilePlaceholder(v: unknown): v is FilePlaceholder {
  return isPlainObject(v) && v._kind === 'file'
}

function looksLikeImageUrl(s: unknown): s is string {
  if (typeof s !== 'string') return false
  if (s.startsWith('data:image/')) return true
  const low = s.toLowerCase()
  const path = low.split('?')[0] ?? low
  return (
    (low.startsWith('http://') || low.startsWith('https://')) &&
    ['.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp'].some((ext) => path.endsWith(ext))
  )
}

function parseContent(content: unknown): ContentPart[] {
  if (content === null || content === undefined) return []
  if (typeof content === 'string') {
    return content.length > 0 ? [{ kind: 'text', text: content }] : []
  }
  if (Array.isArray(content)) {
    const out: ContentPart[] = []
    for (const part of content) {
      if (typeof part === 'string') {
        out.push({ kind: 'text', text: part })
        continue
      }
      if (!isPlainObject(part)) {
        out.push({ kind: 'unknown', json: part })
        continue
      }
      const type = (part.type as string | undefined) ?? ''
      if (type === 'text' || type === 'input_text' || type === 'output_text') {
        const t = (part.text as string | undefined) ?? ''
        if (t) out.push({ kind: 'text', text: t })
        continue
      }
      if (type === 'image_url' || type === 'input_image') {
        const iu = part.image_url
        let url: string | undefined
        let mime: string | null | undefined
        if (typeof iu === 'string') url = iu
        else if (isPlainObject(iu) && typeof iu.url === 'string') url = iu.url
        if (!url && typeof part.url === 'string') url = part.url
        if (!url && typeof (part as Record<string, unknown>).image === 'string')
          url = (part as Record<string, unknown>).image as string
        if (typeof part.mime_type === 'string') mime = part.mime_type
        if (url) {
          out.push({ kind: 'image', url, mime: mime ?? inferMimeFromUrl(url) })
          continue
        }
      }
      if (type === 'file' || type === 'input_file') {
        const file = part.file
        if (isFilePlaceholder(file)) {
          out.push({ kind: 'file', placeholder: file })
          continue
        }
        if (isPlainObject(file)) {
          out.push({
            kind: 'file',
            placeholder: {
              _kind: 'file',
              name: (file.filename as string | undefined) ?? (file.name as string | undefined) ?? null,
              mime: (file.mime_type as string | undefined) ?? (file.mime as string | undefined) ?? null,
              headPreview: typeof file.file_data === 'string' ? String(file.file_data).slice(0, 256) : '',
              truncated: true,
            },
          })
          continue
        }
      }
      if (isFilePlaceholder(part)) {
        out.push({ kind: 'file', placeholder: part })
        continue
      }
      if (looksLikeImageUrl(part)) {
        out.push({ kind: 'image', url: part as unknown as string })
        continue
      }
      out.push({ kind: 'unknown', json: part })
    }
    return out
  }
  if (isFilePlaceholder(content)) {
    return [{ kind: 'file', placeholder: content }]
  }
  return [{ kind: 'unknown', json: content }]
}

function inferMimeFromUrl(url: string): string | null {
  if (url.startsWith('data:')) {
    const m = url.match(/^data:([^;,]+)/)
    return m?.[1] ?? null
  }
  const path = (url.split('?')[0] ?? url).toLowerCase()
  if (path.endsWith('.png')) return 'image/png'
  if (path.endsWith('.jpg') || path.endsWith('.jpeg')) return 'image/jpeg'
  if (path.endsWith('.webp')) return 'image/webp'
  if (path.endsWith('.gif')) return 'image/gif'
  if (path.endsWith('.bmp')) return 'image/bmp'
  return null
}

function estimateBytesFromDataUrl(url: string): number | null {
  if (!url.startsWith('data:')) return null
  const idx = url.indexOf(',')
  if (idx < 0) return null
  const b64 = url.slice(idx + 1)
  return Math.floor((b64.length * 3) / 4)
}

function formatBytes(n: number | null | undefined): string {
  if (n == null || !isFinite(n) || n < 0) return '—'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(2)} MB`
  return `${(n / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

function safeJsonStringify(v: unknown): string {
  try {
    return JSON.stringify(v, null, 2)
  } catch {
    return String(v)
  }
}

function partJsonText(part: ContentPart): string {
  const value = part.kind === 'unknown' ? part.json : part
  return safeJsonStringify(value)
}

function tryParseJson(s: string): unknown | undefined {
  try {
    return JSON.parse(s)
  } catch {
    return undefined
  }
}

// ---------------------------------------------------------------------------
// build cards
// ---------------------------------------------------------------------------

const source = computed(() => props.record.source)

type ParsedRequest = {
  messageCards: MessageCard[]
  toolDefs: ToolDef[]
  programCard: {
    method: string
    url: string
    summary: Record<string, unknown>
  } | null
}

const parsedRequest = computed<ParsedRequest>(() => {
  const rec = props.record
  const body = rec.requestBody
  const cards: MessageCard[] = []
  const tools: ToolDef[] = []
  let programCard: ParsedRequest['programCard'] = null

  if (source.value === 'llm' && isPlainObject(body) && Array.isArray(body.messages)) {
    for (const m of body.messages) {
      if (!isPlainObject(m)) continue
      const role = (m.role as string | undefined) ?? 'user'
      const parts = parseContent(m.content)
      const normalizedRole: Role = role === 'tool' ? 'tool' : ((['system', 'user', 'assistant'].includes(role) ? role : 'user') as Role)
      cards.push({
        role: normalizedRole,
        label: role.toUpperCase(),
        name: (m.name as string | undefined) ?? null,
        parts,
        tool_call_id: (m.tool_call_id as string | undefined) ?? null,
      })
    }
    if (Array.isArray(body.tools)) {
      for (const t of body.tools) {
        if (!isPlainObject(t)) continue
        if (t.type === 'function' && isPlainObject(t.function)) {
          tools.push({
            name: (t.function.name as string | undefined) ?? '(unnamed)',
            description: (t.function.description as string | undefined) ?? null,
            parameters: t.function.parameters,
          })
        } else if (typeof t.name === 'string') {
          tools.push({
            name: t.name,
            description: (t.description as string | undefined) ?? null,
            parameters: (t.parameters as unknown) ?? null,
          })
        }
      }
    }
  } else {
    // program 请求：无 messages
    const summary: Record<string, unknown> = {}
    if (body !== undefined && body !== null && body !== '') summary.body = body
    programCard = {
      method: rec.method,
      url: rec.url,
      summary,
    }
  }

  return { messageCards: cards, toolDefs: tools, programCard }
})

type ParsedResponse = {
  kind: 'assistant' | 'error' | 'generic'
  parts: ContentPart[]
  toolCalls: ToolCallCard[]
  toolReturns: ToolReturnCard[]
  raw: unknown
}

const parsedResponse = computed<ParsedResponse>(() => {
  const rec = props.record
  const status = rec.responseStatus ?? 0
  const body = rec.responseBody

  // 1. LLM 成功：aggregated 结构 { _aggregated: true, content, reasoning_content?, tool_calls? }
  if (
    source.value === 'llm' &&
    isPlainObject(body) &&
    (body._aggregated === true || typeof body.content === 'string' || Array.isArray(body.tool_calls))
  ) {
    const parts: ContentPart[] = []
    if (typeof body.content === 'string' && body.content) parts.push({ kind: 'text', text: body.content })
    if (typeof body.reasoning_content === 'string' && body.reasoning_content) {
      parts.push({ kind: 'text', text: '[reasoning]\n' + body.reasoning_content })
    }
    const toolCalls: ToolCallCard[] = []
    if (Array.isArray(body.tool_calls)) {
      for (const tc of body.tool_calls) {
        if (!isPlainObject(tc) || !isPlainObject(tc.function)) continue
        const args = (tc.function.arguments as string | undefined) ?? ''
        toolCalls.push({
          id: (tc.id as string | undefined) ?? undefined,
          name: (tc.function.name as string | undefined) ?? '(unnamed)',
          argumentsRaw: args,
          argumentsParsed: typeof args === 'string' ? tryParseJson(args) : args,
        })
      }
    }
    return { kind: 'assistant', parts, toolCalls, toolReturns: [], raw: body }
  }

  // 2. LLM openai 非流式 message 结构：choices[0].message
  if (source.value === 'llm' && isPlainObject(body) && Array.isArray(body.choices) && body.choices.length > 0) {
    const choice = body.choices[0]
    const message = isPlainObject(choice) ? (choice.message as Record<string, unknown> | undefined) : undefined
    if (isPlainObject(message)) {
      const parts: ContentPart[] = parseContent(message.content)
      const toolCalls: ToolCallCard[] = []
      const reasoning = message.reasoning_content ?? message.reasoning
      if (typeof reasoning === 'string' && reasoning) {
        parts.push({ kind: 'text', text: '[reasoning]\n' + reasoning })
      }
      if (Array.isArray(message.tool_calls)) {
        for (const tc of message.tool_calls) {
          if (!isPlainObject(tc) || !isPlainObject(tc.function)) continue
          const args = (tc.function.arguments as string | undefined) ?? ''
          toolCalls.push({
            id: (tc.id as string | undefined) ?? undefined,
            name: (tc.function.name as string | undefined) ?? '(unnamed)',
            argumentsRaw: args,
            argumentsParsed: typeof args === 'string' ? tryParseJson(args) : args,
          })
        }
      }
      return { kind: 'assistant', parts, toolCalls, toolReturns: [], raw: body }
    }
  }

  // 3. 错误：状态码 >= 400 或有 error 字段
  if (status >= 400 || rec.error) {
    const parts: ContentPart[] = []
    if (rec.error) parts.push({ kind: 'text', text: rec.error })
    if (body !== undefined && body !== null && body !== '') {
      if (typeof body === 'string') parts.push({ kind: 'text', text: body })
      else parts.push({ kind: 'text', text: safeJsonStringify(body) })
    }
    return { kind: 'error', parts, toolCalls: [], toolReturns: [], raw: body }
  }

  // 4. 通用响应：update 下载结果 / 其它
  const parts: ContentPart[] = []
  if (body !== undefined && body !== null && body !== '') {
    if (typeof body === 'string') parts.push({ kind: 'text', text: body })
    else parts.push({ kind: 'text', text: safeJsonStringify(body) })
  }
  return { kind: 'generic', parts, toolCalls: [], toolReturns: [], raw: body }
})

// 来自请求 messages 的 tool 消息（role=tool）归入工具区底部
const toolReturnCards = computed<ToolReturnCard[]>(() => {
  const rec = props.record
  if (source.value !== 'llm') return []
  const body = rec.requestBody
  if (!isPlainObject(body) || !Array.isArray(body.messages)) return []
  const out: ToolReturnCard[] = []
  for (const m of body.messages) {
    if (!isPlainObject(m)) continue
    if (m.role !== 'tool') continue
    out.push({
      name: (m.name as string | undefined) ?? null,
      tool_call_id: (m.tool_call_id as string | undefined) ?? null,
      parts: parseContent(m.content),
    })
  }
  return out
})

// 顶部 assistant 的 tool_calls（来自请求消息，非响应）
const assistantToolCallCards = computed<ToolCallCard[]>(() => {
  const rec = props.record
  if (source.value !== 'llm') return []
  const body = rec.requestBody
  if (!isPlainObject(body) || !Array.isArray(body.messages)) return []
  const out: ToolCallCard[] = []
  for (const m of body.messages) {
    if (!isPlainObject(m) || m.role !== 'assistant') continue
    const calls = m.tool_calls
    if (!Array.isArray(calls)) continue
    for (const tc of calls) {
      if (!isPlainObject(tc) || !isPlainObject(tc.function)) continue
      const args = (tc.function.arguments as string | undefined) ?? ''
      out.push({
        id: (tc.id as string | undefined) ?? undefined,
        name: (tc.function.name as string | undefined) ?? '(unnamed)',
        argumentsRaw: args,
        argumentsParsed: typeof args === 'string' ? tryParseJson(args) : args,
      })
    }
  }
  return out
})

// 过滤掉只有 role=tool 的消息卡（因为进入工具区）
const visibleMessageCards = computed(() => parsedRequest.value.messageCards.filter((c) => c.role !== 'tool'))

function roleBarColor(role: Role): string {
  switch (role) {
    case 'system':
      return 'bg-[var(--color-warning)]'
    case 'user':
      return 'bg-[var(--color-brand)]'
    case 'assistant':
      return 'bg-[var(--color-success)]'
    case 'program':
      return 'bg-[var(--color-text-muted)]'
    case 'response':
      return 'bg-[var(--color-info)]'
    case 'tool':
      return 'bg-[var(--color-purple)]'
    default:
      return 'bg-[var(--color-text-muted)]'
  }
}

function roleLabelClass(role: Role): string {
  const common = 'inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold tracking-wider'
  switch (role) {
    case 'system':
      return `${common} bg-[var(--color-warning-bg)] text-[var(--color-warning-text)]`
    case 'user':
      return `${common} bg-brand-a20 text-[var(--color-brand)]`
    case 'assistant':
      return `${common} bg-[var(--color-success-bg)] text-[var(--color-success-text)]`
    case 'program':
      return `${common} bg-surface-muted text-[var(--color-text-secondary)]`
    case 'response':
      return `${common} bg-[var(--color-info-bg)] text-[var(--color-info-text)]`
    case 'tool':
      return `${common} bg-[var(--color-purple-bg)] text-[var(--color-purple-text)]`
    default:
      return common
  }
}

function shouldUseCodeViewer(text: string): boolean {
  return text.length > 1200 || text.split('\n').length > 40
}

function describeImage(url: string, mime?: string | null, bytes?: number | null): string {
  const m = mime ?? inferMimeFromUrl(url) ?? 'image'
  const b = bytes ?? estimateBytesFromDataUrl(url)
  return b != null ? `${m} · ${formatBytes(b)}` : m
}

function openImage(url: string) {
  try {
    window.open(url, '_blank', 'noopener,noreferrer')
  } catch {
    /* noop */
  }
}

function formatToolArgs(card: ToolCallCard): string {
  if (card.argumentsParsed !== undefined) {
    return safeJsonStringify(card.argumentsParsed)
  }
  return card.argumentsRaw
}

function formatToolParams(parameters: unknown): string {
  if (parameters === undefined || parameters === null) return ''
  return safeJsonStringify(parameters)
}

function parameterProperties(parameters: unknown): Array<{ key: string; type: string; required: boolean; description?: string }> {
  if (!isPlainObject(parameters)) return []
  const props_ = parameters.properties
  if (!isPlainObject(props_)) return []
  const required = Array.isArray(parameters.required) ? new Set(parameters.required as string[]) : new Set<string>()
  const out: Array<{ key: string; type: string; required: boolean; description?: string }> = []
  for (const [k, v] of Object.entries(props_)) {
    if (!isPlainObject(v)) {
      out.push({ key: k, type: 'any', required: required.has(k) })
      continue
    }
    const t = (v.type as string | undefined) ?? 'any'
    out.push({ key: k, type: t, required: required.has(k), description: v.description as string | undefined })
  }
  return out
}
</script>

<template>
  <div class="flex flex-col gap-2.5">
    <!-- 请求区 -->
    <div v-if="parsedRequest.programCard" class="http-card">
      <div :class="['http-card-bar', roleBarColor('program')]" />
      <div class="http-card-body">
        <div class="mb-1.5 flex flex-wrap items-center gap-2">
          <span :class="roleLabelClass('program')">PROGRAM</span>
          <span class="font-mono text-[11px] text-[var(--color-text-secondary)]">{{ parsedRequest.programCard.method }}</span>
          <span class="break-all text-xs text-[var(--color-text)]">{{ parsedRequest.programCard.url }}</span>
        </div>
        <div v-if="Object.keys(parsedRequest.programCard.summary).length > 0">
          <CodeViewer
            :model-value="safeJsonStringify(parsedRequest.programCard.summary)"
            language="json"
            :fold-level="2"
            max-height-class="max-h-[40vh]"
          />
        </div>
        <div v-else class="text-xs text-[var(--color-text-muted)]">无请求体</div>
      </div>
    </div>

    <div
      v-for="(card, idx) in visibleMessageCards"
      :key="'m-' + idx"
      class="http-card"
    >
      <div :class="['http-card-bar', roleBarColor(card.role)]" />
      <div class="http-card-body">
        <div class="mb-1.5 flex flex-wrap items-center gap-2">
          <span :class="roleLabelClass(card.role)">{{ card.label }}</span>
          <span v-if="card.name" class="text-[11px] text-[var(--color-text-secondary)]">name: {{ card.name }}</span>
          <span v-if="card.tool_call_id" class="text-[11px] text-[var(--color-text-muted)]">tool_call_id: {{ card.tool_call_id }}</span>
        </div>
        <div v-if="card.parts.length === 0" class="text-xs italic text-[var(--color-text-muted)]">（空内容）</div>
        <div v-for="(part, pi) in card.parts" :key="'p-' + pi" class="mb-1.5 last:mb-0">
          <template v-if="part.kind === 'text'">
            <CodeViewer
              :model-value="part.text"
              :language="tryParseJson(part.text) !== undefined ? 'json' : 'plain'"
              :fold-level="2"
              max-height-class="max-h-[40vh]"
            />
          </template>
          <template v-else-if="part.kind === 'image'">
            <div class="flex flex-col gap-1">
              <img
                :src="part.url"
                :alt="describeImage(part.url, part.mime, part.bytesHint)"
                class="cursor-zoom-in rounded-md border border-[var(--color-border-subtle)] bg-[var(--color-surface-overlay)]"
                style="max-width: 220px; max-height: 160px; object-fit: contain"
                @click="openImage(part.url)"
              />
              <span class="text-[11px] text-[var(--color-text-muted)]">
                <ImageIcon class="inline h-3 w-3" />
                {{ describeImage(part.url, part.mime, part.bytesHint) }}
              </span>
            </div>
          </template>
          <template v-else-if="part.kind === 'file'">
            <div class="rounded-md border border-[var(--color-border-subtle)] bg-[var(--color-surface-overlay)]/30 p-2">
              <div class="mb-1 flex items-center gap-1.5 text-xs text-[var(--color-text)]">
                <FileText class="h-3.5 w-3.5 text-[var(--color-text-secondary)]" />
                <span class="font-medium">{{ part.placeholder.name || '&lt;unnamed&gt;' }}</span>
                <span class="text-[11px] text-[var(--color-text-muted)]">
                  {{ part.placeholder.mime || '—' }} · {{ formatBytes(part.placeholder.bytes ?? null) }}
                </span>
              </div>
              <pre class="max-h-40 overflow-auto whitespace-pre-wrap break-words rounded bg-[var(--color-dark-surface)] px-2 py-1 font-mono text-[11px] text-[var(--color-text-secondary)]">{{ part.placeholder.headPreview || '' }}</pre>
              <div class="mt-0.5 text-right text-[10px] text-[var(--color-text-muted)]">
                …内容已截断（隐私保护）
              </div>
            </div>
          </template>
          <template v-else>
            <CodeViewer
              :model-value="partJsonText(part)"
              language="json"
              :fold-level="2"
              max-height-class="max-h-[40vh]"
            />
          </template>
        </div>
      </div>
    </div>

    <!-- 响应区 -->
    <div class="http-card">
      <div :class="['http-card-bar', roleBarColor('response')]" />
      <div class="http-card-body">
        <div class="mb-1.5 flex flex-wrap items-center gap-2">
          <span :class="roleLabelClass('response')">RESPONSE</span>
          <span
            v-if="record.responseStatus != null"
            class="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold"
            :class="(record.responseStatus ?? 0) >= 400 ? 'bg-rose-500/15 text-rose-300' : 'bg-emerald-500/10 text-emerald-300'"
          >HTTP {{ record.responseStatus }}</span>
          <span v-if="parsedResponse.kind === 'assistant'" class="text-[11px] text-[var(--color-text-secondary)]">assistant</span>
          <span v-if="parsedResponse.kind === 'error'" class="text-[11px] text-rose-300">error</span>
          <span v-if="record.durationMs != null" class="text-[11px] text-[var(--color-text-muted)]">{{ record.durationMs }} ms</span>
        </div>

        <div v-if="parsedResponse.parts.length === 0" class="text-xs italic text-[var(--color-text-muted)]">
          {{ parsedResponse.kind === 'error' ? '（错误信息为空）' : '（无响应体）' }}
        </div>
        <div v-for="(part, pi) in parsedResponse.parts" :key="'r-' + pi" class="mb-1.5 last:mb-0">
          <template v-if="part.kind === 'text'">
            <CodeViewer
              v-if="shouldUseCodeViewer(part.text)"
              :model-value="part.text"
              :language="tryParseJson(part.text) !== undefined ? 'json' : 'plain'"
              :fold-level="2"
              :show-line-numbers="false"
              max-height-class="max-h-[40vh]"
            />
            <pre
              v-else
              class="whitespace-pre-wrap break-words rounded bg-[var(--color-surface-overlay)]/30 px-2 py-1.5 font-mono text-[12px] leading-relaxed"
              :class="parsedResponse.kind === 'error' ? 'text-[var(--color-error-text)]' : 'text-[var(--color-text-primary)]'"
            >{{ part.text }}</pre>
          </template>
          <template v-else>
            <CodeViewer
              :model-value="partJsonText(part)"
              language="json"
              :fold-level="2"
              max-height-class="max-h-[40vh]"
            />
          </template>
        </div>
      </div>
    </div>

    <!-- 工具区 -->
    <div
      v-if="parsedRequest.toolDefs.length > 0 || assistantToolCallCards.length > 0 || parsedResponse.toolCalls.length > 0 || toolReturnCards.length > 0"
      class="mt-1 border-t border-dashed border-[var(--color-border-subtle)] pt-2"
    >
      <div class="mb-1.5 flex items-center gap-1.5 text-xs text-[var(--color-text-secondary)]">
        <Wrench class="h-3.5 w-3.5" />
        <span>工具区</span>
        <span class="text-[10px] text-[var(--color-text-muted)]">（从请求与响应中提取，人类可读）</span>
      </div>

      <!-- 已挂载工具 -->
      <div v-if="parsedRequest.toolDefs.length > 0" class="mb-2 flex flex-col gap-1.5">
        <div class="text-[11px] text-[var(--color-text-muted)]">已挂载工具 · {{ parsedRequest.toolDefs.length }}</div>
        <div
          v-for="(tool, ti) in parsedRequest.toolDefs"
          :key="'td-' + ti"
          class="http-card"
        >
          <div :class="['http-card-bar', roleBarColor('tool')]" />
          <div class="http-card-body">
            <div class="mb-1 flex flex-wrap items-center gap-2">
              <span :class="roleLabelClass('tool')">TOOL</span>
              <span class="font-mono text-xs text-[var(--color-text-primary)]">{{ tool.name }}</span>
            </div>
            <div v-if="tool.description" class="mb-1 text-xs text-[var(--color-text-secondary)]">{{ tool.description }}</div>
            <div v-if="parameterProperties(tool.parameters).length > 0" class="space-y-0.5">
              <div
                v-for="(p, pi) in parameterProperties(tool.parameters)"
                :key="'pp-' + pi"
                class="flex flex-wrap items-center gap-1.5 text-[11px]"
              >
                <span class="font-mono text-[var(--color-brand)]">{{ p.key }}</span>
                <span class="text-[var(--color-text-muted)]">:</span>
                <span class="font-mono text-emerald-300">{{ p.type }}</span>
                <span v-if="p.required" class="rounded bg-rose-500/15 px-1 text-[10px] text-rose-300">required</span>
                <span v-if="p.description" class="text-[var(--color-text-secondary)]">— {{ p.description }}</span>
              </div>
            </div>
            <div v-else-if="tool.parameters" class="mt-1">
              <CodeViewer
                :model-value="formatToolParams(tool.parameters)"
                language="json"
                :fold-level="2"
                max-height-class="max-h-[30vh]"
              />
            </div>
          </div>
        </div>
      </div>

      <!-- 工具调用（来自 assistant 消息或响应） -->
      <div
        v-if="assistantToolCallCards.length > 0 || parsedResponse.toolCalls.length > 0"
        class="mb-2 flex flex-col gap-1.5"
      >
        <div class="text-[11px] text-[var(--color-text-muted)]">工具调用</div>
        <div
          v-for="(call, ci) in [...assistantToolCallCards, ...parsedResponse.toolCalls]"
          :key="'tc-' + ci"
          class="http-card"
        >
          <div :class="['http-card-bar', roleBarColor('tool')]" />
          <div class="http-card-body">
            <div class="mb-1 flex flex-wrap items-center gap-2">
              <span :class="roleLabelClass('tool')">TOOL CALL</span>
              <span class="font-mono text-xs text-[var(--color-text-primary)]">{{ call.name }}()</span>
              <span v-if="call.id" class="text-[10px] text-[var(--color-text-muted)]">id: {{ call.id }}</span>
            </div>
            <CodeViewer
              :model-value="formatToolArgs(call)"
              language="json"
              :fold-level="2"
              max-height-class="max-h-[30vh]"
            />
          </div>
        </div>
      </div>

      <!-- 工具返回 -->
      <div v-if="toolReturnCards.length > 0" class="flex flex-col gap-1.5">
        <div class="text-[11px] text-[var(--color-text-muted)]">工具返回</div>
        <div
          v-for="(ret, ri) in toolReturnCards"
          :key="'tr-' + ri"
          class="http-card"
        >
          <div :class="['http-card-bar', roleBarColor('tool')]" />
          <div class="http-card-body">
            <div class="mb-1 flex flex-wrap items-center gap-2">
              <span :class="roleLabelClass('tool')">TOOL RETURN</span>
              <span v-if="ret.name" class="font-mono text-xs text-[var(--color-text-primary)]">{{ ret.name }}</span>
              <span v-if="ret.tool_call_id" class="text-[10px] text-[var(--color-text-muted)]">call id: {{ ret.tool_call_id }}</span>
            </div>
            <div v-for="(part, pi) in ret.parts" :key="'tr-p-' + pi" class="mb-1 last:mb-0">
              <template v-if="part.kind === 'text'">
                <CodeViewer
                  :model-value="part.text"
                  :language="tryParseJson(part.text) !== undefined ? 'json' : 'plain'"
                  :fold-level="2"
                  max-height-class="max-h-[30vh]"
                />
              </template>
              <template v-else-if="part.kind === 'file'">
                <div class="rounded-md border border-[var(--color-border-subtle)] bg-[var(--color-surface-overlay)]/30 p-2">
                  <div class="mb-1 flex items-center gap-1.5 text-xs">
                    <FileText class="h-3.5 w-3.5" />
                    <span class="font-medium">{{ part.placeholder.name || '&lt;unnamed&gt;' }}</span>
                    <span class="text-[11px] text-[var(--color-text-muted)]">{{ part.placeholder.mime || '—' }} · {{ formatBytes(part.placeholder.bytes ?? null) }}</span>
                  </div>
                  <pre class="max-h-40 overflow-auto whitespace-pre-wrap break-words rounded bg-[var(--color-dark-surface)] px-2 py-1 font-mono text-[11px] text-[var(--color-text-secondary)]">{{ part.placeholder.headPreview || '' }}</pre>
                  <div class="mt-0.5 text-right text-[10px] text-[var(--color-text-muted)]">…内容已截断（隐私保护）</div>
                </div>
              </template>
              <template v-else>
                <CodeViewer
                  :model-value="partJsonText(part)"
                  language="json"
                  :fold-level="2"
                  max-height-class="max-h-[30vh]"
                />
              </template>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.http-card {
  position: relative;
  display: flex;
  min-width: 0;
  border-radius: 0.5rem;
  background-color: color-mix(in srgb, var(--color-surface-muted) 60%, transparent);
  border: 1px solid var(--color-border-subtle);
  overflow: hidden;
}

.http-card-bar {
  width: 3px;
  flex-shrink: 0;
}

.http-card-body {
  flex: 1;
  min-width: 0;
  padding: 0.5rem 0.75rem 0.625rem 0.75rem;
}
</style>
