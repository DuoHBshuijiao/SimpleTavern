// @vitest-environment happy-dom
import { describe, expect, it } from 'vitest'
import { createApp, ref, type App } from 'vue'
import { useChatSearch } from './useChatSearch'

type SearchApi = ReturnType<typeof useChatSearch>
type TestOptions = Omit<Parameters<typeof useChatSearch>[0], 'chatSearchInputRef'>

// 在真实 setup 上下文中运行 composable，使 watch / onBeforeUnmount 等生命周期生效。
function withSetup(options: TestOptions): { api: SearchApi; app: App } {
  let api!: SearchApi
  const app = createApp({
    setup() {
      api = useChatSearch({ ...options, chatSearchInputRef: ref(null) })
      return () => null
    },
  })
  app.mount(document.createElement('div'))
  return { api, app }
}

describe('useChatSearch', () => {
  it('在结果间循环导航并跳转到对应消息序号', () => {
    const jumps: number[] = []
    const { api, app } = withSetup({
      getActiveChat: () => null,
      jumpToMessageIndex: (i) => jumps.push(i),
    })
    api.chatSearchResults.value = [
      { messageId: 'a', messageIndex: 5, snippet: '' },
      { messageId: 'b', messageIndex: 8, snippet: '' },
    ]
    api.goToNextSearchResult()
    expect(api.chatSearchCursor.value).toBe(0)
    api.goToNextSearchResult()
    expect(api.chatSearchCursor.value).toBe(1)
    api.goToNextSearchResult()
    expect(api.chatSearchCursor.value).toBe(0)
    api.goToPrevSearchResult()
    expect(api.chatSearchCursor.value).toBe(1)
    expect(jumps).toEqual([5, 8, 5, 8])
    app.unmount()
  })

  it('jumpToSearchResult 设置游标并跳转，越界则忽略', () => {
    const jumps: number[] = []
    const { api, app } = withSetup({
      getActiveChat: () => null,
      jumpToMessageIndex: (i) => jumps.push(i),
    })
    api.chatSearchResults.value = [
      { messageId: 'a', messageIndex: 3, snippet: '' },
      { messageId: 'b', messageIndex: 9, snippet: '' },
    ]
    api.jumpToSearchResult(1)
    expect(api.chatSearchCursor.value).toBe(1)
    api.jumpToSearchResult(5)
    expect(api.chatSearchCursor.value).toBe(1)
    expect(jumps).toEqual([9])
    app.unmount()
  })

  it('chatSearchHitsForNav 优先用结果，否则回退到 chip 行', () => {
    const { api, app } = withSetup({
      getActiveChat: () => null,
      jumpToMessageIndex: () => {},
    })
    api.chatSearchChipsDisplayHits.value = [{ messageId: 'c', messageIndex: 2, snippet: '' }]
    expect(api.chatSearchHitsForNav.value.map((h) => h.messageIndex)).toEqual([2])
    api.chatSearchResults.value = [{ messageId: 'a', messageIndex: 7, snippet: '' }]
    expect(api.chatSearchHitsForNav.value.map((h) => h.messageIndex)).toEqual([7])
    app.unmount()
  })

  it('无活动会话时 runChatSearch 清空结果且不发请求', async () => {
    const { api, app } = withSetup({
      getActiveChat: () => null,
      jumpToMessageIndex: () => {},
    })
    api.chatSearchResults.value = [{ messageId: 'a', messageIndex: 1, snippet: '' }]
    api.chatSearchCursor.value = 0
    api.chatSearchQuery.value = 'hello'
    await api.runChatSearch()
    expect(api.chatSearchResults.value).toEqual([])
    expect(api.chatSearchCursor.value).toBe(-1)
    app.unmount()
  })

  it('resetChatSearchForChatSwitch 清空搜索状态', () => {
    const { api, app } = withSetup({
      getActiveChat: () => null,
      jumpToMessageIndex: () => {},
    })
    api.showChatSearch.value = true
    api.chatSearchQuery.value = 'x'
    api.chatSearchResults.value = [{ messageId: 'a', messageIndex: 1, snippet: '' }]
    api.chatSearchCursor.value = 0
    api.resetChatSearchForChatSwitch()
    expect(api.showChatSearch.value).toBe(false)
    expect(api.chatSearchQuery.value).toBe('')
    expect(api.chatSearchResults.value).toEqual([])
    expect(api.chatSearchCursor.value).toBe(-1)
    app.unmount()
  })
})
