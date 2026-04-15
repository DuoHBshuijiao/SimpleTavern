import { reactive } from 'vue'

const RUNTIME_STORAGE_KEY = 'simpletavern:webgpuBackgroundRuntime:v1'
const PREVIEW_DRAFT_PREFIX = 'simpletavern:webgpuDraft:'

export interface WebGpuRuntimeState {
  hasOverride: boolean
  enabled: boolean
  activePresetId: string | null
  nonce: number
}

const runtimeState = reactive<WebGpuRuntimeState>({
  hasOverride: false,
  enabled: false,
  activePresetId: null,
  nonce: 0,
})

let runtimeLoaded = false

function safeReadSessionStorage(key: string): string | null {
  try {
    return sessionStorage.getItem(key)
  } catch {
    return null
  }
}

function safeWriteSessionStorage(key: string, value: string | null): void {
  try {
    if (value == null) sessionStorage.removeItem(key)
    else sessionStorage.setItem(key, value)
  } catch {
    // ignore
  }
}

function loadRuntimeIfNeeded() {
  if (runtimeLoaded) return
  runtimeLoaded = true
  const raw = safeReadSessionStorage(RUNTIME_STORAGE_KEY)
  if (!raw) return
  try {
    const parsed = JSON.parse(raw) as Partial<WebGpuRuntimeState>
    runtimeState.hasOverride = true
    runtimeState.enabled = parsed.enabled === true
    runtimeState.activePresetId =
      typeof parsed.activePresetId === 'string' && parsed.activePresetId.trim()
        ? parsed.activePresetId.trim()
        : null
  } catch {
    // ignore invalid cache
  }
}

function persistRuntime() {
  safeWriteSessionStorage(
    RUNTIME_STORAGE_KEY,
    JSON.stringify({
      enabled: runtimeState.enabled,
      activePresetId: runtimeState.activePresetId,
    }),
  )
}

export function useWebGpuBackgroundRuntime() {
  loadRuntimeIfNeeded()

  function setRuntime(next: { enabled: boolean; activePresetId: string | null }) {
    runtimeState.hasOverride = true
    runtimeState.enabled = next.enabled
    runtimeState.activePresetId = next.activePresetId
    runtimeState.nonce += 1
    persistRuntime()
  }

  function clearRuntime() {
    runtimeState.hasOverride = false
    runtimeState.enabled = false
    runtimeState.activePresetId = null
    runtimeState.nonce += 1
    safeWriteSessionStorage(RUNTIME_STORAGE_KEY, null)
  }

  return {
    runtimeState,
    setRuntime,
    clearRuntime,
  }
}

export function getWebGpuDraftCacheKey(presetId: string): string {
  return `${PREVIEW_DRAFT_PREFIX}${presetId}`
}

export function readWebGpuDraftSource(presetId: string): string | null {
  if (!presetId) return null
  return safeReadSessionStorage(getWebGpuDraftCacheKey(presetId))
}

export function writeWebGpuDraftSource(presetId: string, source: string | null): void {
  if (!presetId) return
  safeWriteSessionStorage(getWebGpuDraftCacheKey(presetId), source)
}
