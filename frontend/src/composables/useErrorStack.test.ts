import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/http'
import { useErrorStack } from './useErrorStack'


afterEach(() => {
  vi.useRealTimers()
})


describe('useErrorStack typed error', () => {
  it('保留 suggestedAction、requestId 与 code', () => {
    vi.useFakeTimers()
    const stack = useErrorStack()
    const error = new ApiError({
      code: 'provider_auth_failed',
      message: '鉴权失败',
      source: 'llm',
      retryable: false,
      requestId: 'req_stack_123',
      suggestedAction: '检查 API Key',
    })

    stack.pushError({ message: error, source: 'main' })

    expect(stack.items.value[0]).toMatchObject({
      message: '鉴权失败',
      code: 'provider_auth_failed',
      requestId: 'req_stack_123',
      suggestedAction: '检查 API Key',
      title: '聊天错误',
    })
    stack.clearAll()
  })

  it('继续兼容旧字符串错误', () => {
    vi.useFakeTimers()
    const stack = useErrorStack()

    stack.pushError({ message: 'legacy error', source: 'assistant' })

    expect(stack.items.value[0]).toMatchObject({
      message: 'legacy error',
      title: '助手错误',
    })
    stack.clearAll()
  })
})
