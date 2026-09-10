/**
 * T-822：协议自适应预览（「这次会怎么发」）。
 *
 * 输入一组响应式参数（baseUrl / model / protocol / promptCache / 深度 / Fast），
 * 去抖后调用 /api/llm/resolve-preview，输出 ProtocolResolution；
 * 供聊天面板 ModelControlPanel 与预设编辑器共用。
 */
import { computed, ref, shallowRef, watch, type Ref } from 'vue'
import { resolvePreview, type ProtocolResolution, type ResolvePreviewRequest } from '../api/llm'

export const PROMPT_CACHE_MODE_LABELS: Record<string, string> = {
  auto: '自动',
  off: '关闭',
  implicit: '隐式',
  explicit: '显式断点',
  best_effort: '尽力而为',
}

export interface UseProtocolPreviewOptions {
  /** 为 false 时不发请求（例如弹层未打开） */
  enabled?: Ref<boolean> | (() => boolean)
  debounceMs?: number
}

export function useProtocolPreview(
  source: () => ResolvePreviewRequest | null,
  options: UseProtocolPreviewOptions = {},
) {
  const preview = shallowRef<ProtocolResolution | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  let timer: ReturnType<typeof setTimeout> | null = null
  let controller: AbortController | null = null
  let seq = 0

  const isEnabled = () => {
    const e = options.enabled
    if (e == null) return true
    return typeof e === 'function' ? e() : e.value
  }

  async function run() {
    const body = source()
    if (!body || !body.model?.trim()) {
      preview.value = null
      loading.value = false
      return
    }
    controller?.abort()
    controller = new AbortController()
    const mySeq = ++seq
    loading.value = true
    error.value = null
    try {
      const result = await resolvePreview(body, controller.signal)
      if (mySeq !== seq) return
      preview.value = result
    } catch (err) {
      if (mySeq !== seq) return
      if ((err as { name?: string })?.name === 'AbortError') return
      error.value = err instanceof Error ? err.message : String(err)
      preview.value = null
    } finally {
      if (mySeq === seq) loading.value = false
    }
  }

  function schedule() {
    if (!isEnabled()) return
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => {
      timer = null
      void run()
    }, options.debounceMs ?? 180)
  }

  watch(
    () => [isEnabled(), JSON.stringify(source())] as const,
    ([enabled]) => {
      if (enabled) schedule()
    },
    { immediate: true },
  )

  /** 可用思考档位；未拿到预览前给全档位，避免弹层闪空 */
  const availableEfforts = computed(() => preview.value?.availableEfforts ?? [])
  const supportsFastMode = computed(() => preview.value?.supportsFastMode ?? false)
  const adjustments = computed(() => preview.value?.adjustments ?? [])

  return { preview, loading, error, availableEfforts, supportsFastMode, adjustments, refresh: run }
}

/** 调整项的中文短语（弹层 / 预设编辑器共用） */
export function describeAdjustment(adj: { type: string; from?: string | null; to?: string | null; reason?: string | null }): string {
  switch (adj.type) {
    case 'protocol_switched':
      return `协议自动切换：${adj.from ?? '?'} → ${adj.to ?? '?'}`
    case 'protocol_kept':
      return `保持 ${adj.to ?? '?'}（供应商未声明支持 ${adj.from ?? '?'}）`
    case 'reasoning_effort_clamped':
      return `思考深度 ${adj.from ?? '?'} → ${adj.to ?? '?'}`
    case 'fast_mode_unsupported':
      return adj.reason || '该模型 / 供应商不支持 Fast 模式，已忽略'
    case 'sampling_dropped':
      return adj.reason || '该模型不接受 temperature / top_p，已忽略'
    case 'cache_mode_auto':
      return `缓存策略自动选择：${PROMPT_CACHE_MODE_LABELS[adj.to ?? ''] ?? adj.to ?? '?'}`
    case 'cache_mode_downgraded':
      return `缓存策略 ${PROMPT_CACHE_MODE_LABELS[adj.from ?? ''] ?? adj.from} → ${PROMPT_CACHE_MODE_LABELS[adj.to ?? ''] ?? adj.to}${adj.reason ? `（${adj.reason}）` : ''}`
    case 'cache_ttl_translated':
      return `缓存 TTL ${adj.from ?? '?'} → ${adj.to ?? '?'}${adj.reason ? `（${adj.reason}）` : ''}`
    case 'cache_key_fallback':
      return `缓存键 ${adj.from ?? '?'} → ${adj.to ?? '?'}${adj.reason ? `（${adj.reason}）` : ''}`
    case 'cache_disabled':
      return adj.reason || '供应商不提供提示词缓存'
    case 'base_url_rewritten':
      return `接口地址按协议改写：${adj.to ?? ''}`
    default:
      return adj.reason || adj.type
  }
}
