// @vitest-environment happy-dom
import { beforeEach, describe, expect, it } from 'vitest'
import { createApp, type App } from 'vue'
import { useImageStickyBinding } from './useImageStickyBinding'
import type { Chat } from '../types/models'

type Api = ReturnType<typeof useImageStickyBinding>

function chat(id: string, model?: string, presetId?: string | null): Chat {
  return {
    id,
    overrides: { params: model ? { model } : {}, presetId: presetId ?? undefined },
  } as unknown as Chat
}

function withSetup(
  getActiveChat: () => Chat | null,
  getDefaultModel: () => string | undefined = () => '',
): { api: Api; app: App } {
  let api!: Api
  const app = createApp({
    setup() {
      api = useImageStickyBinding({ getActiveChat, getDefaultModel })
      return () => null
    },
  })
  app.mount(document.createElement('div'))
  return { api, app }
}

describe('useImageStickyBinding', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('resolveImageBindingKey 使用会话模型，缺失时回退默认模型', () => {
    const { api, app } = withSetup(() => chat('c1', 'gpt-x', 'p1'))
    expect(api.resolveImageBindingKey()).toEqual({ chatId: 'c1', model: 'gpt-x', presetId: 'p1' })
    app.unmount()

    const { api: api2, app: app2 } = withSetup(() => chat('c2', undefined, null), () => 'def-model')
    expect(api2.resolveImageBindingKey()).toEqual({ chatId: 'c2', model: 'def-model', presetId: null })
    app2.unmount()
  })

  it('resolveImageBindingKey 无会话返回 null', () => {
    const { api, app } = withSetup(() => null)
    expect(api.resolveImageBindingKey()).toBeNull()
    app.unmount()
  })

  it('isImageStickyActive 仅当绑定与当前键完全一致时为真', () => {
    const { api, app } = withSetup(() => chat('c1', 'm1', 'p1'))
    expect(api.isImageStickyActive()).toBe(false)
    api.imageStickyBinding.value = { chatId: 'c1', model: 'm1', presetId: 'p1' }
    expect(api.isImageStickyActive()).toBe(true)
    api.imageStickyBinding.value = { chatId: 'c1', model: 'other', presetId: 'p1' }
    expect(api.isImageStickyActive()).toBe(false)
    app.unmount()
  })

  it('saveImageStickyBindingRow 持久化到 localStorage', () => {
    const { api, app } = withSetup(() => chat('c1', 'm1', 'p1'))
    api.saveImageStickyBindingRow({ chatId: 'c1', model: 'm1', presetId: 'p1' })
    const raw = JSON.parse(localStorage.getItem('SimpleTavern:imageStickyBinding:v1') || '{}')
    expect(raw.c1).toEqual({ model: 'm1', presetId: 'p1' })
    app.unmount()
  })

  it('openImageFallback 设置回退对话框状态', () => {
    const { api, app } = withSetup(() => null)
    expect(api.imageFallbackDialog.value.visible).toBe(false)
    const retry = async () => {}
    api.openImageFallback('boom', retry)
    expect(api.imageFallbackDialog.value.visible).toBe(true)
    expect(api.imageFallbackDialog.value.error).toBe('boom')
    expect(api.imageFallbackDialog.value.retryAction).toBe(retry)
    app.unmount()
  })
})
