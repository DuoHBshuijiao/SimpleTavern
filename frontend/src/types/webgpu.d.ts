declare type GPUAdapter = any
declare type GPUDevice = any
declare type GPUCanvasContext = any
declare type GPURenderPipeline = any
declare type GPUBindGroup = any
declare type GPUBuffer = any
declare type GPUShaderModule = any
declare type GPUUncapturedErrorEvent = any

declare const GPUBufferUsage: {
  UNIFORM: number
  COPY_DST: number
}

interface Navigator {
  gpu?: {
    requestAdapter: () => Promise<GPUAdapter | null>
    getPreferredCanvasFormat: () => string
  }
}
