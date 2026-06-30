// @vitest-environment happy-dom
import { describe, expect, it, vi, afterEach } from 'vitest'
import { createApp, nextTick, ref, type App, type Ref } from 'vue'
import { HEADER_LIFT_MS } from '../constants/chatHeaderMorph'
import { useChatHeaderLayout } from './useChatHeaderLayout'

type Api = ReturnType<typeof useChatHeaderLayout>

function withSetup(opts?: {
  sidebarCollapsed?: Ref<boolean>
  isNarrowPortrait?: Ref<boolean>
}): { api: Api; app: App; sidebarCollapsed: Ref<boolean> } {
  let api!: Api
  const sidebarCollapsed = opts?.sidebarCollapsed ?? ref(false)
  const isNarrowPortrait = opts?.isNarrowPortrait ?? ref(false)
  const app = createApp({
    setup() {
      api = useChatHeaderLayout({
        sidebarCollapsed,
        isNarrowPortrait,
        isTtsEnabled: () => true,
      })
      return () => null
    },
  })
  app.mount(document.createElement('div'))
  return { api, app, sidebarCollapsed }
}

describe('useChatHeaderLayout', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('侧栏收起后 morph 链：inset → lifting → full', async () => {
    vi.useFakeTimers()
    const { api, app, sidebarCollapsed } = withSetup()
    sidebarCollapsed.value = true
    await nextTick()
    expect(api.headerMorphPhase.value).toBe('inset')
    vi.advanceTimersByTime(1000)
    expect(api.headerMorphPhase.value).toBe('lifting')
    vi.advanceTimersByTime(HEADER_LIFT_MS)
    expect(api.headerMorphPhase.value).toBe('full')
    app.unmount()
  })

  it('full 阶段 chatHeaderStyle 拉满宽且直角', () => {
    const { api, app, sidebarCollapsed } = withSetup()
    sidebarCollapsed.value = true
    api.headerMorphPhase.value = 'full'
    expect(api.chatHeaderStyle.value.left).toBe('0')
    expect(api.chatHeaderStyle.value.borderRadius).toBe('0')
    app.unmount()
  })

  it('ttsInputSinkActive 在 lifting/full 且侧栏收起时为 true', () => {
    const { api, app, sidebarCollapsed } = withSetup()
    sidebarCollapsed.value = true
    api.headerMorphPhase.value = 'lifting'
    expect(api.ttsInputSinkActive.value).toBe(true)
    api.headerMorphPhase.value = 'inset'
    expect(api.ttsInputSinkActive.value).toBe(false)
    app.unmount()
  })
})
