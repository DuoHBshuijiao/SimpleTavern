// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, apiGet, parseApiError } from './http'


afterEach(() => {
  vi.unstubAllGlobals()
})


describe('HTTP typed error contract', () => {
  it('解析统一 envelope 与响应 requestId', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            code: 'provider_quota_exceeded',
            message: '额度不足',
            source: 'llm',
            retryable: true,
            suggestedAction: '检查账户额度',
          }),
          {
            status: 429,
            headers: {
              'Content-Type': 'application/json',
              'X-Request-Id': 'req_http_123',
            },
          },
        ),
      ),
    )

    const error = await apiGet('/api/example').catch((value: unknown) => value)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({
      code: 'provider_quota_exceeded',
      message: '额度不足',
      retryable: true,
      requestId: 'req_http_123',
      suggestedAction: '检查账户额度',
      status: 429,
    })
  })

  it('兼容旧 FastAPI detail 与裸文本错误', () => {
    const detailError = parseApiError('{"detail":{"code":"chat_not_found","message":"会话不存在"}}', {
      status: 404,
      requestId: 'req_detail_123',
    })
    const textError = parseApiError('legacy failure', { status: 500 })

    expect(detailError).toMatchObject({
      code: 'chat_not_found',
      message: '会话不存在',
      requestId: 'req_detail_123',
    })
    expect(textError).toMatchObject({
      code: 'request_failed',
      message: 'legacy failure',
      status: 500,
    })
  })

  it('兼容旧请求校验 detail 数组', () => {
    const error = parseApiError(
      {
        detail: [{ loc: ['body', 'count'], msg: 'Input should be a valid integer' }],
      },
      { status: 422 },
    )

    expect(error.code).toBe('request_validation_failed')
    expect(error.message).toBe('请求参数无效')
  })
})
