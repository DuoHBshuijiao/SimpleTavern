/**
 * 页面内 WebGPU 可用性探测（与 chrome://gpu 全局状态可能不一致）。
 */

export type WebGpuUnavailableReason =
  | 'insecure_context'
  | 'no_navigator_gpu'
  | 'adapter_null'
  | 'canvas_timeout'
  | 'context_null'
  | 'device_failed'
  | 'unknown'

export type WebGpuAdapterProbeResult =
  | { ok: true }
  | {
      ok: false
      reason: 'insecure_context' | 'no_navigator_gpu' | 'adapter_null' | 'unknown'
    }

/** 非安全上下文下页面通常拿不到 navigator.gpu，与 chrome://gpu 无关 */
export function isWebGpuLikelyBlockedByContext(): boolean {
  return typeof window !== 'undefined' && !window.isSecureContext
}

export function getWebGpuUnavailableMessage(reason: WebGpuUnavailableReason): string {
  switch (reason) {
    case 'insecure_context':
      return '当前页面不是安全上下文，页面内无法使用 WebGPU。请使用 https，或通过 localhost / 127.0.0.1 访问（不要用局域网 IP 的 http）。'
    case 'no_navigator_gpu':
      return '当前页面未暴露 navigator.gpu（可能被策略禁用或与 chrome://gpu 报告不一致）。'
    case 'adapter_null':
      return '未能获得 WebGPU 适配器（可能被省电策略、多 GPU 切换或驱动限制影响）。'
    case 'canvas_timeout':
      return '画布未就绪，WebGPU 初始化超时。若反复出现请刷新页面。'
    case 'context_null':
      return '无法创建 WebGPU 画布上下文。'
    case 'device_failed':
      return 'WebGPU 设备创建失败。'
    case 'unknown':
    default:
      return 'WebGPU 初始化失败。'
  }
}

/**
 * 仅探测：安全上下文 + navigator.gpu + requestAdapter（不创建 device、不依赖 canvas）。
 * 用于设置页「适配器状态」与编译前快速检查。
 */
export async function probeWebGpuAdapter(): Promise<WebGpuAdapterProbeResult> {
  if (typeof window === 'undefined') return { ok: false, reason: 'unknown' }
  if (!window.isSecureContext) return { ok: false, reason: 'insecure_context' }
  const gpu = navigator.gpu
  if (!gpu) return { ok: false, reason: 'no_navigator_gpu' }
  try {
    const adapter = await gpu.requestAdapter()
    if (!adapter) return { ok: false, reason: 'adapter_null' }
    return { ok: true }
  } catch {
    return { ok: false, reason: 'unknown' }
  }
}
