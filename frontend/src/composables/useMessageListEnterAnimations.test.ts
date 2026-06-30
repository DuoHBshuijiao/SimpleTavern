// @vitest-environment happy-dom
import { describe, expect, it, vi, afterEach } from 'vitest'
import { createApp, type App } from 'vue'
import { useMessageListEnterAnimations } from './useMessageListEnterAnimations'

type Api = ReturnType<typeof useMessageListEnterAnimations>

function withSetup(): { api: Api; app: App } {
  let api!: Api
  const app = createApp({
    setup() {
      api = useMessageListEnterAnimations()
      return () => null
    },
  })
  app.mount(document.createElement('div'))
  return { api, app }
}

describe('useMessageListEnterAnimations', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('arm 后定时结束自动清除 user id', () => {
    vi.useFakeTimers()
    const { api, app } = withSetup()
    api.armUserMessageEnterAnimation('u1')
    expect(api.entrancingUserMessageId.value).toBe('u1')
    vi.advanceTimersByTime(480)
    expect(api.entrancingUserMessageId.value).toBeNull()
    app.unmount()
  })

  it('clearMessageListEnterAnimations 取消 user 与 assistant 定时器', () => {
    vi.useFakeTimers()
    const { api, app } = withSetup()
    api.armUserMessageEnterAnimation('u1')
    api.armAssistantRowEnterAnimation('a1')
    api.clearMessageListEnterAnimations()
    expect(api.entrancingUserMessageId.value).toBeNull()
    expect(api.entrancingAssistantMessageId.value).toBeNull()
    vi.advanceTimersByTime(500)
    expect(api.entrancingUserMessageId.value).toBeNull()
    expect(api.entrancingAssistantMessageId.value).toBeNull()
    app.unmount()
  })
})
