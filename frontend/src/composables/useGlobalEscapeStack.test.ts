// @vitest-environment happy-dom
import { describe, expect, it } from 'vitest'
import { createCloseTopOverlayHandler, useGlobalEscapeStack } from './useGlobalEscapeStack'

describe('createCloseTopOverlayHandler', () => {
  it('notify host 存在时直接消费 Esc', () => {
    const close = createCloseTopOverlayHandler({
      hasActiveNotifyHost: () => true,
      tryCloseErrorStack: () => true,
      overlayClosers: [],
    })
    expect(close()).toBe(true)
  })

  it('按顺序尝试 overlay closers', () => {
    const log: string[] = []
    const close = createCloseTopOverlayHandler({
      hasActiveNotifyHost: () => false,
      tryCloseErrorStack: () => {
        log.push('error')
        return false
      },
      overlayClosers: [
        () => {
          log.push('a')
          return false
        },
        () => {
          log.push('b')
          return true
        },
        () => {
          log.push('c')
          return true
        },
      ],
    })
    expect(close()).toBe(true)
    expect(log).toEqual(['error', 'a', 'b'])
  })
})

describe('useGlobalEscapeStack', () => {
  it('叠层关闭成功时 preventDefault 且不调 fallback', () => {
    let fallback = 0
    const { handleGlobalKeydown } = useGlobalEscapeStack({
      closeTopOverlay: () => true,
      onEscapeFallback: () => {
        fallback += 1
      },
    })
    const e = new KeyboardEvent('keydown', { key: 'Escape', cancelable: true })
    handleGlobalKeydown(e)
    expect(e.defaultPrevented).toBe(true)
    expect(fallback).toBe(0)
  })

  it('无叠层时执行 fallback', () => {
    let fallback = 0
    const { handleGlobalKeydown } = useGlobalEscapeStack({
      closeTopOverlay: () => false,
      onEscapeFallback: () => {
        fallback += 1
      },
    })
    handleGlobalKeydown(new KeyboardEvent('keydown', { key: 'Escape' }))
    expect(fallback).toBe(1)
  })
})
