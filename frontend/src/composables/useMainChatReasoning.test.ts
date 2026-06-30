// @vitest-environment happy-dom
import { describe, expect, it } from 'vitest'
import { createApp, ref, type App } from 'vue'
import { useMainChatReasoning } from './useMainChatReasoning'
import type { Chat } from '../types/models'

type Api = ReturnType<typeof useMainChatReasoning>

function withSetup(getActiveChat: () => Chat | null | undefined): { api: Api; app: App } {
  let api!: Api
  const app = createApp({
    setup() {
      api = useMainChatReasoning({ getActiveChat })
      return () => null
    },
  })
  app.mount(document.createElement('div'))
  return { api, app }
}

describe('useMainChatReasoning', () => {
  it('getReasoningForMessageId 优先返回流式当前条', () => {
    const { api, app } = withSetup(() => null)
    api.chatReasoningMessageId.value = 'm1'
    api.chatReasoningContent.value = 'thinking…'
    expect(api.getReasoningForMessageId('m1')).toBe('thinking…')
    app.unmount()
  })

  it('pushCurrentReasoningToBlocks 写入 assistant 消息与 blocks', () => {
    const chat = ref<Chat>({
      id: 'c1',
      characterId: 'char',
      messages: [{ id: 'a1', role: 'assistant', content: '' }],
      overrides: {},
      createdAt: '',
      updatedAt: '',
    } as Chat)
    const { api, app } = withSetup(() => chat.value)
    api.chatReasoningMessageId.value = 'a1'
    api.chatReasoningContent.value = 'chain'
    api.chatReasoningElapsedSec.value = 1.2
    api.pushCurrentReasoningToBlocks('a1')
    expect(chat.value.messages[0]?.reasoningContent).toBe('chain')
    expect(chat.value.messages[0]?.reasoningDurationSec).toBe(1.2)
    expect(api.chatReasoningBlocks.value).toEqual([{ messageId: 'a1', content: 'chain' }])
    expect(api.chatReasoningContent.value).toBe('')
    app.unmount()
  })

  it('clearReasoningForChatSwitch 重置全部临时状态', () => {
    const { api, app } = withSetup(() => null)
    api.chatReasoningBlocks.value = [{ messageId: 'x', content: 'y' }]
    api.chatReasoningContent.value = 'z'
    api.chatReasoningMessageId.value = 'x'
    api.chatReasoningStreamActive.value = true
    api.markReasoningStreamPhaseStart()
    api.clearReasoningForChatSwitch()
    expect(api.chatReasoningBlocks.value).toEqual([])
    expect(api.chatReasoningContent.value).toBe('')
    expect(api.chatReasoningMessageId.value).toBeNull()
    expect(api.chatReasoningStreamActive.value).toBe(false)
    app.unmount()
  })
})
