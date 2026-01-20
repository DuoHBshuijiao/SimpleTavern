export type SseEvent = { event: string; data: any }

function parseEventBlock(block: string): SseEvent | null {
  const lines = block.split('\n').map((l) => l.trimEnd())
  let event = 'message'
  const dataLines: string[] = []
  for (const line of lines) {
    if (!line) continue
    if (line.startsWith('event:')) {
      event = line.slice('event:'.length).trim()
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice('data:'.length).trim())
    }
  }
  if (!dataLines.length) return null
  const dataStr = dataLines.join('\n')
  try {
    return { event, data: JSON.parse(dataStr) }
  } catch {
    return { event, data: dataStr }
  }
}

function findSseSeparatorIndex(buffer: string): { idx: number; sepLen: number } | null {
  const idxLf = buffer.indexOf('\n\n')
  const idxCrLf = buffer.indexOf('\r\n\r\n')
  if (idxLf < 0 && idxCrLf < 0) return null
  if (idxLf >= 0 && idxCrLf >= 0) {
    return idxLf <= idxCrLf ? { idx: idxLf, sepLen: 2 } : { idx: idxCrLf, sepLen: 4 }
  }
  if (idxLf >= 0) return { idx: idxLf, sepLen: 2 }
  return { idx: idxCrLf, sepLen: 4 }
}

export async function postAndConsumeSse(
  path: string,
  body: unknown,
  onEvent: (evt: SseEvent) => void,
  signal?: AbortSignal,
) {
  const r = await fetch(path, {
    method: 'POST',
    headers: {
      Accept: 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
    signal,
  })
  if (!r.ok) throw new Error(await r.text())
  if (!r.body) return

  const reader = r.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let processedEventsSinceYield = 0

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    while (true) {
      const sep = findSseSeparatorIndex(buffer)
      if (!sep) break
      const chunk = buffer.slice(0, sep.idx)
      buffer = buffer.slice(sep.idx + sep.sepLen)
      const evt = parseEventBlock(chunk)
      if (evt) {
        onEvent(evt)
        processedEventsSinceYield += 1
        // 让出主线程给渲染：避免某些代理/缓冲导致一次性读到大量 SSE 时 UI “憋到最后才更新”
        if (processedEventsSinceYield >= 20) {
          processedEventsSinceYield = 0
          await new Promise<void>((resolve) => setTimeout(resolve, 0))
        }
      }
    }
  }
}


