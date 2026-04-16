import { computed, onBeforeUnmount, onMounted, ref, watch, type Ref } from 'vue'

import {
  getWebGpuUnavailableMessage,
  type WebGpuUnavailableReason,
} from '../utils/webgpuProbe'
import { normalizeWgslSource } from '../utils/normalizeWgslSource'
import {
  compilationMessagesToDiagnostics,
  filterDiagnosticsBySeverity,
  formatDiagnosticsAsText,
  type WgslCompilationMessageLike,
} from '../utils/wgslCompilation'

type HeaderMorphPhase = 'inset' | 'lifting' | 'full'

export interface WebGpuUnavailableDetail {
  reason: WebGpuUnavailableReason
  message: string
}

export interface WebGpuBackgroundOptions {
  canvasRef: Ref<HTMLCanvasElement | null>
  enabled: Ref<boolean>
  shaderFilename: Ref<string | null>
  headerMorphPhase: Ref<HeaderMorphPhase>
  /** 目标帧率（与设置中的白名单一致），实际受显示器刷新率约束 */
  targetFps: Ref<number>
  /** 仅在确认无法使用 WebGPU 时调用（不会因画布尚未挂载而误报） */
  onUnavailable?: (detail: WebGpuUnavailableDetail) => void
}

/**
 * Uniform 约定（MVP）：
 * - tail 默认填 0，未来字段追加时保持尾部扩展兼容
 * - 同时提供 CSS 与物理像素分辨率（resolutionCss/resolutionPhysical）
 * - 尾部含 frameCounter、对齐槽、mouseNorm、immersiveBlend（见 WEBGPU_UNIFORM_CONTRACT.md）
 * - WGSL struct Uniforms 在 immersiveBlend 后按 8 字节对齐，实际 56 字节；索引 13 为 WGSL 尾部 padding，恒 0
 */
const UNIFORM_FLOAT_COUNT = 14
const UNIFORM_BYTE_SIZE = UNIFORM_FLOAT_COUNT * 4
const hiddenTabFrameIntervalMs = 1000
/** 等待 canvas 挂载的最大帧数（约 2s @60fps） */
const maxCanvasWaitFrames = 120

function preferredCanvasFormat(): string {
  return navigator.gpu?.getPreferredCanvasFormat() || 'bgra8unorm'
}

export function useWebGpuBackground(options: WebGpuBackgroundOptions) {
  const isSupported = ref<boolean | null>(null)
  const isRunning = ref(false)
  const compileError = ref<string | null>(null)
  const runtimeError = ref<string | null>(null)

  let adapter: GPUAdapter | null = null
  let device: GPUDevice | null = null
  let context: GPUCanvasContext | null = null
  let pipeline: GPURenderPipeline | null = null
  let bindGroup: GPUBindGroup | null = null
  /** 固定 @group(0) @binding(0) uniform，避免 layout:auto 在 uniform 被优化剔除后得到空布局 */
  let uniformBindGroupLayout: ReturnType<GPUDevice['createBindGroupLayout']> | null = null
  let webGpuBgPipelineLayout: ReturnType<GPUDevice['createPipelineLayout']> | null = null
  let uniformBuffer: GPUBuffer | null = null
  let shaderModule: GPUShaderModule | null = null
  let currentShaderFilename: string | null = null

  let animationFrameId = 0
  let lostHandler: ((event: GPUUncapturedErrorEvent) => void) | null = null
  let lastFrameMs = 0
  let frameCounter = 0
  let unavailableNotified = false
  /** ensureDevice 最后一次失败原因（供回调使用，避免启发式误判） */
  let lastEnsureFailureReason: WebGpuUnavailableReason = 'unknown'

  /** 相对画布 CSS 盒的归一化坐标 [0,1]，指针未移动过时为画布中心 */
  let lastMouseNormX = 0.5
  let lastMouseNormY = 0.5
  let pointerMoveHandler: ((ev: PointerEvent) => void) | null = null
  /** 向 immersive 目标平滑，供着色器做缓动（与 WEBGPU_UNIFORM_CONTRACT.md 一致） */
  let immersiveBlendSmooth = 0

  const uniformFloats = new Float32Array(UNIFORM_FLOAT_COUNT)

  const immersive01 = computed(() => (options.headerMorphPhase.value === 'full' ? 1 : 0))

  function stopLoop() {
    if (animationFrameId) {
      cancelAnimationFrame(animationFrameId)
      animationFrameId = 0
    }
    isRunning.value = false
  }

  function clearGpuState() {
    stopLoop()
    if (pointerMoveHandler) {
      window.removeEventListener('pointermove', pointerMoveHandler)
      pointerMoveHandler = null
    }
    if (lostHandler && device) {
      device.removeEventListener('uncapturederror', lostHandler as EventListener)
    }
    lostHandler = null
    shaderModule = null
    bindGroup = null
    pipeline = null
    uniformBindGroupLayout = null
    webGpuBgPipelineLayout = null
    if (uniformBuffer) {
      uniformBuffer.destroy()
      uniformBuffer = null
    }
    if (device) {
      try {
        device.destroy()
      } catch {
        // ignore
      }
    }
    device = null
    adapter = null
    context = null
    currentShaderFilename = null
    immersiveBlendSmooth = 0
  }

  function attachPointerTracking() {
    if (pointerMoveHandler) return
    pointerMoveHandler = (ev: PointerEvent) => {
      const canvas = options.canvasRef.value
      if (!canvas) return
      const rect = canvas.getBoundingClientRect()
      const w = Math.max(1, rect.width)
      const h = Math.max(1, rect.height)
      const nx = (ev.clientX - rect.left) / w
      const ny = (ev.clientY - rect.top) / h
      lastMouseNormX = Math.min(1, Math.max(0, nx))
      lastMouseNormY = Math.min(1, Math.max(0, ny))
    }
    window.addEventListener('pointermove', pointerMoveHandler)
  }

  function resizeCanvas() {
    const canvas = options.canvasRef.value
    if (!canvas || !device || !context) return
    const cssWidth = Math.max(1, Math.floor(canvas.clientWidth || window.innerWidth || 1))
    const cssHeight = Math.max(1, Math.floor(canvas.clientHeight || window.innerHeight || 1))
    const dpr = Math.max(1, window.devicePixelRatio || 1)
    const physicalWidth = Math.max(1, Math.floor(cssWidth * dpr))
    const physicalHeight = Math.max(1, Math.floor(cssHeight * dpr))
    if (canvas.width !== physicalWidth || canvas.height !== physicalHeight) {
      canvas.width = physicalWidth
      canvas.height = physicalHeight
      context.configure({
        device,
        format: preferredCanvasFormat(),
        alphaMode: 'opaque',
      })
    }
  }

  /**
   * 等待 Vue 挂载与 v-if 渲染后的 canvas ref（不触发 onUnavailable）。
   */
  async function waitForCanvas(): Promise<HTMLCanvasElement | null> {
    for (let i = 0; i < maxCanvasWaitFrames; i++) {
      const el = options.canvasRef.value
      if (el) return el
      await new Promise<void>((resolve) => {
        requestAnimationFrame(() => resolve())
      })
    }
    return options.canvasRef.value
  }

  async function ensureDevice(): Promise<boolean> {
    if (device && context) return true

    if (typeof window !== 'undefined' && !window.isSecureContext) {
      lastEnsureFailureReason = 'insecure_context'
      isSupported.value = false
      return false
    }

    const gpu = navigator.gpu
    if (!gpu) {
      lastEnsureFailureReason = 'no_navigator_gpu'
      isSupported.value = false
      return false
    }

    const canvas = await waitForCanvas()
    if (!canvas) {
      lastEnsureFailureReason = 'canvas_timeout'
      isSupported.value = false
      return false
    }

    adapter = await gpu.requestAdapter()
    if (!adapter) {
      lastEnsureFailureReason = 'adapter_null'
      isSupported.value = false
      return false
    }

    try {
      device = await adapter.requestDevice()
    } catch {
      lastEnsureFailureReason = 'device_failed'
      isSupported.value = false
      adapter = null
      return false
    }

    context = canvas.getContext('webgpu')
    if (!context) {
      lastEnsureFailureReason = 'context_null'
      isSupported.value = false
      try {
        device.destroy()
      } catch {
        // ignore
      }
      device = null
      adapter = null
      return false
    }
    context.configure({
      device,
      format: preferredCanvasFormat(),
      alphaMode: 'opaque',
    })
    uniformBuffer = device.createBuffer({
      label: 'webgpu-bg-uniforms',
      size: UNIFORM_BYTE_SIZE,
      usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST,
    })
    uniformBindGroupLayout = device.createBindGroupLayout({
      label: 'webgpu-bg-uniform-bgl',
      entries: [
        {
          binding: 0,
          // GPUShaderStage.VERTEX | GPUShaderStage.FRAGMENT
          visibility: 3,
          buffer: { type: 'uniform', hasDynamicOffset: false, minBindingSize: UNIFORM_BYTE_SIZE },
        },
      ],
    })
    webGpuBgPipelineLayout = device.createPipelineLayout({
      label: 'webgpu-bg-pipeline-layout',
      bindGroupLayouts: [uniformBindGroupLayout],
    })
    lostHandler = (event: GPUUncapturedErrorEvent) => {
      runtimeError.value = event.error?.message || 'WebGPU runtime error'
    }
    device.addEventListener('uncapturederror', lostHandler as EventListener)
    isSupported.value = true
    return true
  }

  async function fetchShaderSource(filename: string): Promise<string> {
    const res = await fetch(`/api/shader-presets/${encodeURIComponent(filename)}`, {
      method: 'GET',
      headers: { Accept: 'text/plain' },
    })
    if (!res.ok) {
      throw new Error(`shader fetch failed: ${res.status}`)
    }
    return await res.text()
  }

  async function buildPipeline(shaderFilename: string) {
    if (!device || !uniformBuffer || !uniformBindGroupLayout || !webGpuBgPipelineLayout) return
    const source = normalizeWgslSource(await fetchShaderSource(shaderFilename))
    shaderModule = device.createShaderModule({
      code: source,
      label: `webgpu-bg-${shaderFilename}`,
    })
    const info = await shaderModule.getCompilationInfo()
    const errors = info.messages.filter(
      (item: WgslCompilationMessageLike) => item.type === 'error',
    )
    if (errors.length > 0) {
      const diags = compilationMessagesToDiagnostics(errors)
      const onlyErr = filterDiagnosticsBySeverity(diags, 'error')
      throw new Error(formatDiagnosticsAsText(onlyErr))
    }
    pipeline = device.createRenderPipeline({
      label: 'webgpu-background-pipeline',
      layout: webGpuBgPipelineLayout,
      vertex: { module: shaderModule, entryPoint: 'vs_main' },
      fragment: {
        module: shaderModule,
        entryPoint: 'fs_main',
        targets: [{ format: preferredCanvasFormat() }],
      },
      primitive: { topology: 'triangle-list' },
    })
    bindGroup = device.createBindGroup({
      layout: uniformBindGroupLayout,
      entries: [{ binding: 0, resource: { buffer: uniformBuffer } }],
    })
    currentShaderFilename = shaderFilename
  }

  function drawFrame(nowMs: number) {
    if (!device || !context || !uniformBuffer) return
    animationFrameId = requestAnimationFrame(drawFrame)
    if (document.hidden && lastFrameMs > 0 && nowMs - lastFrameMs < hiddenTabFrameIntervalMs) {
      return
    }
    const fps = Math.max(1, options.targetFps.value)
    const minFrameMs = 1000 / fps
    if (lastFrameMs > 0 && nowMs - lastFrameMs < minFrameMs - 0.25) {
      return
    }
    const deltaMs = lastFrameMs > 0 ? nowMs - lastFrameMs : 16.67
    lastFrameMs = nowMs
    frameCounter += 1
    resizeCanvas()
    const canvas = options.canvasRef.value
    if (!canvas) return

    const dpr = Math.max(1, window.devicePixelRatio || 1)
    const cssWidth = Math.max(1, Math.floor(canvas.clientWidth || window.innerWidth || 1))
    const cssHeight = Math.max(1, Math.floor(canvas.clientHeight || window.innerHeight || 1))
    const physicalWidth = Math.max(1, Math.floor(cssWidth * dpr))
    const physicalHeight = Math.max(1, Math.floor(cssHeight * dpr))

    const deltaSec = Math.max(0.001, deltaMs * 0.001)
    const immersiveTarget = immersive01.value
    const k = 6.0
    immersiveBlendSmooth +=
      (immersiveTarget - immersiveBlendSmooth) * (1 - Math.exp(-k * deltaSec))
    if (immersiveTarget === 1 && immersiveBlendSmooth > 0.9995) immersiveBlendSmooth = 1
    if (immersiveTarget === 0 && immersiveBlendSmooth < 0.0005) immersiveBlendSmooth = 0

    uniformFloats.fill(0)
    uniformFloats[0] = nowMs * 0.001
    uniformFloats[1] = immersiveTarget
    uniformFloats[2] = dpr
    uniformFloats[3] = deltaSec
    uniformFloats[4] = cssWidth
    uniformFloats[5] = cssHeight
    uniformFloats[6] = physicalWidth
    uniformFloats[7] = physicalHeight
    uniformFloats[8] = frameCounter
    uniformFloats[9] = 0
    uniformFloats[10] = lastMouseNormX
    uniformFloats[11] = lastMouseNormY
    uniformFloats[12] = immersiveBlendSmooth
    uniformFloats[13] = 0 // WGSL struct 末尾对齐，与 minBindingSize 一致
    device.queue.writeBuffer(uniformBuffer, 0, uniformFloats)

    const encoder = device.createCommandEncoder({ label: 'webgpu-background-pass' })
    const texture = context.getCurrentTexture()
    const pass = encoder.beginRenderPass({
      colorAttachments: [
        {
          view: texture.createView(),
          clearValue: { r: 0, g: 0, b: 0, a: 1 },
          loadOp: 'clear',
          storeOp: 'store',
        },
      ],
    })
    if (pipeline && bindGroup) {
      pass.setPipeline(pipeline)
      pass.setBindGroup(0, bindGroup)
      pass.draw(3, 1, 0, 0)
    }
    pass.end()
    device.queue.submit([encoder.finish()])
  }

  async function startIfNeeded() {
    const enabled = options.enabled.value
    const shaderFilename = options.shaderFilename.value
    if (!enabled) {
      clearGpuState()
      compileError.value = null
      runtimeError.value = null
      unavailableNotified = false
      isSupported.value = null
      return
    }
    const ready = await ensureDevice()
    if (!ready) {
      const reason = lastEnsureFailureReason
      const message = getWebGpuUnavailableMessage(reason)
      if (!unavailableNotified) {
        unavailableNotified = true
        options.onUnavailable?.({ reason, message })
      }
      clearGpuState()
      return
    }
    runtimeError.value = null
    if (shaderFilename && shaderFilename !== currentShaderFilename) {
      try {
        await buildPipeline(shaderFilename)
        compileError.value = null
      } catch (error) {
        pipeline = null
        bindGroup = null
        compileError.value = error instanceof Error ? error.message : String(error)
      }
    } else if (!shaderFilename) {
      pipeline = null
      bindGroup = null
      currentShaderFilename = null
      compileError.value = null
    }
    if (!animationFrameId) {
      lastFrameMs = 0
      frameCounter = 0
      lastMouseNormX = 0.5
      lastMouseNormY = 0.5
      immersiveBlendSmooth = immersive01.value
      attachPointerTracking()
      animationFrameId = requestAnimationFrame(drawFrame)
      isRunning.value = true
    }
  }

  watch(
    () => [
      options.enabled.value,
      options.shaderFilename.value,
      options.canvasRef.value,
      options.headerMorphPhase.value,
      options.targetFps.value,
    ],
    () => {
      void startIfNeeded()
    },
    { immediate: true },
  )

  onMounted(() => {
    void startIfNeeded()
    window.addEventListener('resize', resizeCanvas)
  })

  onBeforeUnmount(() => {
    window.removeEventListener('resize', resizeCanvas)
    clearGpuState()
  })

  return {
    isSupported,
    isRunning,
    compileError,
    runtimeError,
  }
}
