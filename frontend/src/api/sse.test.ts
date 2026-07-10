// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from './http'
import { postAndConsumeSse, type SseEvent } from './sse'


function sseResponse(body: string, requestId = 'req_sse_header'): Response {
  const encoder = new TextEncoder()
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(encoder.encode(body))
      controller.close()
    },
  })
  return new Response(stream, {
    status: 200,
    headers: {
      'Content-Type': 'text/event-stream',
      'X-Request-Id': requestId,
    },
  })
}


afterEach(() => {
  vi.unstubAllGlobals()
})


describe('SSE terminal error contract', () => {
  it('error 事件转为 typed error，并停止处理后续 done', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        sseResponse(
          [
            'event: meta\ndata: {"requestId":"req_sse_123"}\n\n',
            'event: error\ndata: {"code":"upstream_timeout","message":"上游超时","requestId":"req_sse_123","suggestedAction":"稍后重试","terminal":true}\n\n',
            'event: done\ndata: {"ok":true}\n\n',
          ].join(''),
        ),
      ),
    )
    const events: SseEvent[] = []

    const error = await postAndConsumeSse('/api/generate/stream', {}, (event) => {
      events.push(event)
    }).catch((value: unknown) => value)

    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({
      code: 'upstream_timeout',
      message: '上游超时',
      requestId: 'req_sse_123',
      suggestedAction: '稍后重试',
      terminal: true,
    })
    expect(events.map((event) => event.event)).toEqual(['meta', 'error'])
  })

  it('旧版仅 message 的 error 事件仍按 terminal error 处理', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        sseResponse('event: error\ndata: {"message":"legacy stream failure"}\n\n', 'req_legacy_123'),
      ),
    )

    const error = await postAndConsumeSse('/api/generate/stream', {}, () => {}).catch(
      (value: unknown) => value,
    )

    expect(error).toMatchObject({
      code: 'request_failed',
      message: 'legacy stream failure',
      requestId: 'req_legacy_123',
      terminal: true,
    })
  })
})
