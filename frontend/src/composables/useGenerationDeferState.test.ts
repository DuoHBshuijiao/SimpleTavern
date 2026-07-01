// @vitest-environment happy-dom
import { describe, expect, it, vi } from 'vitest'
import { createApp, type App } from 'vue'
import type { ChatMessage } from '../types/models'
import { useGenerationDeferState } from './useGenerationDeferState'

type Api = ReturnType<typeof useGenerationDeferState>

function msg(id: string): ChatMessage {
  return { id, role: 'user', content: 'x', ts: '2026', version: 1 } as ChatMessage
}

function withSetup(): { api: Api; app: App } {
  let api!: Api
  const app = createApp({
    setup() {
      api = useGenerationDeferState()
      return () => null
    },
  })
  app.mount(document.createElement('div'))
  return { api, app }
}

describe('useGenerationDeferState', () => {
  it('beginSaveSendDefer 同步隐藏与待删 id', () => {
    const { api, app } = withSetup()
    api.beginSaveSendDefer({
      chatId: 'c1',
      tailIdsToDeleteOnSuccess: ['m2', 'm3'],
      mode: 'single',
    })
    expect(api.saveSendDeferCtx.value?.chatId).toBe('c1')
    expect(api.streamHiddenMessageIds.value).toEqual(['m2', 'm3'])
    expect(api.streamDeferDeleteIds.value).toEqual(['m2', 'm3'])
    app.unmount()
  })

  it('filterVisibleMessages 过滤隐藏 id', () => {
    const { api, app } = withSetup()
    api.streamHiddenMessageIds.value = ['b']
    expect(api.filterVisibleMessages([msg('a'), msg('b'), msg('c')]).map((m) => m.id)).toEqual([
      'a',
      'c',
    ])
    app.unmount()
  })

  it('finalizeSaveSendAfterGeneration 成功时删除尾部并清状态', async () => {
    const { api, app } = withSetup()
    const finalizeTailDelete = vi.fn(async () => {})
    api.beginSaveSendDefer({
      chatId: 'c1',
      tailIdsToDeleteOnSuccess: ['tail-1'],
      mode: 'single',
    })
    const handled = await api.finalizeSaveSendAfterGeneration('c1', false, finalizeTailDelete)
    expect(handled).toBe(true)
    expect(finalizeTailDelete).toHaveBeenCalledWith('c1', ['tail-1'])
    expect(api.saveSendDeferCtx.value).toBeNull()
    expect(api.streamHiddenMessageIds.value).toEqual([])
    app.unmount()
  })

  it('finalizeSaveSendAfterGeneration 出错时只清状态不删尾部', async () => {
    const { api, app } = withSetup()
    const finalizeTailDelete = vi.fn(async () => {})
    api.beginSaveSendDefer({
      chatId: 'c1',
      tailIdsToDeleteOnSuccess: ['tail-1'],
      mode: 'single',
    })
    await api.finalizeSaveSendAfterGeneration('c1', true, finalizeTailDelete)
    expect(finalizeTailDelete).not.toHaveBeenCalled()
    expect(api.saveSendDeferCtx.value).toBeNull()
    app.unmount()
  })

  it('beginRewriteDefer 与 takeDeferDeleteIdsAfterRewrite', () => {
    const { api, app } = withSetup()
    api.beginRewriteDefer(
      { chatId: 'c1', anchorId: 'a1', anchorTs: 't', originalMessageId: 'orig' },
      ['a1', 'm2'],
      ['m2'],
    )
    expect(api.rewriteMergeCtx.value?.anchorId).toBe('a1')
    const drop = api.takeDeferDeleteIdsAfterRewrite()
    expect(drop).toEqual(['m2'])
    expect(api.rewriteMergeCtx.value).toBeNull()
    expect(api.streamHiddenMessageIds.value).toEqual([])
    app.unmount()
  })

  it('finalizeRewriteAfterGeneration 出错时只清状态不删尾部', async () => {
    const { api, app } = withSetup()
    const finalizeTailDelete = vi.fn(async () => {})
    api.beginRewriteDefer(
      { chatId: 'c1', anchorId: 'a1', anchorTs: 't', originalMessageId: 'orig' },
      ['a1', 'm2'],
      ['m2'],
    )
    await api.finalizeRewriteAfterGeneration('c1', true, finalizeTailDelete)
    expect(finalizeTailDelete).not.toHaveBeenCalled()
    expect(api.rewriteMergeCtx.value).toBeNull()
    expect(api.streamHiddenMessageIds.value).toEqual([])
    app.unmount()
  })

  it('finalizeRewriteAfterGeneration 成功时删除尾部', async () => {
    const { api, app } = withSetup()
    const finalizeTailDelete = vi.fn(async () => {})
    api.beginRewriteDefer(
      { chatId: 'c1', anchorId: 'a1', anchorTs: 't', originalMessageId: 'orig' },
      ['a1'],
      ['m2'],
    )
    await api.finalizeRewriteAfterGeneration('c1', false, finalizeTailDelete)
    expect(finalizeTailDelete).toHaveBeenCalledWith('c1', ['m2'])
    expect(api.rewriteMergeCtx.value).toBeNull()
    app.unmount()
  })

  it('clearAll 重置全部上下文', () => {
    const { api, app } = withSetup()
    api.beginRewriteDefer(
      { chatId: 'c1', anchorId: 'a1', anchorTs: 't', originalMessageId: 'orig' },
      ['a1'],
      [],
    )
    api.beginSaveSendDefer({ chatId: 'c2', tailIdsToDeleteOnSuccess: ['x'], mode: 'group' })
    api.clearAll()
    expect(api.rewriteMergeCtx.value).toBeNull()
    expect(api.saveSendDeferCtx.value).toBeNull()
    expect(api.streamHiddenMessageIds.value).toEqual([])
    app.unmount()
  })
})
