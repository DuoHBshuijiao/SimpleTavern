// @vitest-environment happy-dom
import { describe, expect, it } from 'vitest'
import { createApp, nextTick, ref, type App } from 'vue'
import { useChatFabSeparation } from './useChatFabSeparation'

describe('useChatFabSeparation', () => {
  it('runChatFabSeparation 重叠时默认调整 TTS top', async () => {
    let assistantTop = 100
    let ttsTop = 105
    const assistantRect = () => new DOMRect(10, assistantTop, 48, 48)
    const ttsRect = () => new DOMRect(10, ttsTop, 48, 48)

    const chatMain = document.createElement('div')
    document.body.appendChild(chatMain)
    Object.defineProperty(chatMain, 'getBoundingClientRect', {
      value: () => new DOMRect(200, 0, 800, 600),
    })

    let api!: ReturnType<typeof useChatFabSeparation>
    const app: App = createApp({
      setup() {
        api = useChatFabSeparation({
          chatMainRef: ref(chatMain),
          chatInputRef: ref({
            getAssistantFabRect: assistantRect,
            setAssistantTopPx: (t) => {
              assistantTop = t
            },
          }),
          ttsPlaybackFabRef: ref({
            getRect: ttsRect,
            setTtsTopPx: (t) => {
              ttsTop = t
            },
          }),
          chatAssistantFabMinTopPx: ref(80),
          sidebarCollapsed: ref(false),
          isNarrowPortrait: ref(false),
          isTtsEnabled: () => true,
        })
        return () => null
      },
    })
    app.mount(document.createElement('div'))
    api.runChatFabSeparation()
    await nextTick()
    expect(ttsTop).not.toBe(105)
    app.unmount()
    chatMain.remove()
  })

  it('TTS 未启用时不执行分离', async () => {
    let ttsMoved = false
    const app = createApp({
      setup() {
        const api = useChatFabSeparation({
          chatMainRef: ref(null),
          chatInputRef: ref({
            getAssistantFabRect: () => new DOMRect(0, 0, 48, 48),
          }),
          ttsPlaybackFabRef: ref({
            getRect: () => new DOMRect(0, 0, 48, 48),
            setTtsTopPx: () => {
              ttsMoved = true
            },
          }),
          chatAssistantFabMinTopPx: ref(0),
          sidebarCollapsed: ref(false),
          isNarrowPortrait: ref(false),
          isTtsEnabled: () => false,
        })
        api.runChatFabSeparation()
        return () => null
      },
    })
    app.mount(document.createElement('div'))
    await nextTick()
    expect(ttsMoved).toBe(false)
    app.unmount()
  })
})
