// @vitest-environment happy-dom
import { describe, expect, it, vi } from 'vitest'
import { createApp, type App } from 'vue'
import { useForkLineage } from './useForkLineage'
import type { Chat, ForkLineageResponse } from '../types/models'

type Api = ReturnType<typeof useForkLineage>

function chat(id: string, forkedFromChatId?: string): Chat {
  return { id, forkedFromChatId } as unknown as Chat
}

function lineage(messageId: string, count: number): ForkLineageResponse {
  return {
    origin: null,
    outgoingForks: [{ messageId, count, chats: [] }],
  } as unknown as ForkLineageResponse
}

function withSetup(options: Parameters<typeof useForkLineage>[0]): { api: Api; app: App } {
  let api!: Api
  const app = createApp({
    setup() {
      api = useForkLineage(options)
      return () => null
    },
  })
  app.mount(document.createElement('div'))
  return { api, app }
}

describe('useForkLineage', () => {
  it('refreshForkLineage 写入结果并停止 loading', async () => {
    const fetchForkLineage = vi.fn(async () => lineage('m1', 2))
    const { api, app } = withSetup({ getActiveChat: () => chat('c1', 'src'), fetchForkLineage })
    await api.refreshForkLineage('c1')
    expect(fetchForkLineage).toHaveBeenCalledWith('c1', expect.any(AbortSignal))
    expect(api.forkLineage.value?.outgoingForks?.[0]?.messageId).toBe('m1')
    expect(api.forkLineageLoading.value).toBe(false)
    app.unmount()
  })

  it('outgoingForksByMessageId 按 messageId 聚合', async () => {
    const { api, app } = withSetup({
      getActiveChat: () => chat('c1', 'src'),
      fetchForkLineage: async () => lineage('m9', 3),
    })
    await api.refreshForkLineage('c1')
    expect(api.outgoingForksByMessageId.value['m9']).toEqual({ count: 3, chats: [] })
    app.unmount()
  })

  it('syncForkLineageForLoadedChat 命中缓存时复用且不重复请求', async () => {
    const fetchForkLineage = vi.fn(async () => lineage('m1', 1))
    const { api, app } = withSetup({ getActiveChat: () => chat('c1', 'src'), fetchForkLineage })
    await api.refreshForkLineage('c1')
    expect(fetchForkLineage).toHaveBeenCalledTimes(1)
    api.syncForkLineageForLoadedChat('c1')
    expect(fetchForkLineage).toHaveBeenCalledTimes(1)
    expect(api.forkLineage.value?.outgoingForks?.[0]?.messageId).toBe('m1')
    app.unmount()
  })

  it('syncForkLineageForLoadedChat 对非分叉会话直接清空', () => {
    const fetchForkLineage = vi.fn(async () => lineage('m1', 1))
    const { api, app } = withSetup({ getActiveChat: () => chat('c2'), fetchForkLineage })
    api.forkLineage.value = lineage('stale', 1)
    api.syncForkLineageForLoadedChat('c2')
    expect(api.forkLineage.value).toBeNull()
    expect(fetchForkLineage).not.toHaveBeenCalled()
    app.unmount()
  })

  it('resetForkLineage 清空展示', async () => {
    const { api, app } = withSetup({
      getActiveChat: () => chat('c1', 'src'),
      fetchForkLineage: async () => lineage('m1', 1),
    })
    await api.refreshForkLineage('c1')
    expect(api.forkLineage.value).not.toBeNull()
    api.resetForkLineage()
    expect(api.forkLineage.value).toBeNull()
    expect(api.forkLineageLoading.value).toBe(false)
    app.unmount()
  })

  it('索引自愈 warning 交给调用方展示', async () => {
    const onWarning = vi.fn()
    const value = lineage('m1', 1)
    value.partialSuccess = true
    value.warnings = [{
      code: 'fork_index_corrupt',
      message: '分叉索引已重建',
      suggestedAction: '检查数据目录',
    }]
    const { api, app } = withSetup({
      getActiveChat: () => chat('c1', 'src'),
      fetchForkLineage: async () => value,
      onWarning,
    })

    await api.refreshForkLineage('c1')

    expect(api.forkLineage.value).toEqual(value)
    expect(onWarning).toHaveBeenCalledWith(value.warnings[0])
    app.unmount()
  })

  it('加载失败交给调用方错误面且清空旧结果', async () => {
    const error = new Error('fork index unavailable')
    const onError = vi.fn()
    const { api, app } = withSetup({
      getActiveChat: () => chat('c1', 'src'),
      fetchForkLineage: async () => {
        throw error
      },
      onError,
    })
    api.forkLineage.value = lineage('stale', 1)

    await api.refreshForkLineage('c1')

    expect(api.forkLineage.value).toBeNull()
    expect(onError).toHaveBeenCalledWith(error)
    app.unmount()
  })
})
