const iconDiscovery = new Map<string, Promise<string | null>>()
const ICON_DISCOVERY_LIMIT = 128
const HTML_PREFIX_LIMIT = 64 * 1024

export function webSourceIconOrigin(address: string): string | null {
  const url = new URL(address)
  const host = url.hostname.toLowerCase().replace(/\.$/, '')
  if (!['http:', 'https:'].includes(url.protocol) || url.port || url.username || url.password ||
      !host.includes('.') || /^[\d.]+$/.test(host) || host.startsWith('[') ||
      /\.(?:localhost|local|internal|lan|home\.arpa)$/.test(host)) return null
  return url.origin
}

async function readPageIcon(origin: string): Promise<string | null> {
  try {
    const response = await fetch(origin, {
      credentials: 'omit',
      referrerPolicy: 'no-referrer',
      redirect: 'error',
      signal: AbortSignal.timeout(3500),
    })
    if (!response.ok || !response.headers.get('content-type')?.includes('text/html') || !response.body) return null
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let html = ''
    try {
      while (html.length < HTML_PREFIX_LIMIT && !/<\/head\s*>/i.test(html)) {
        const { done, value } = await reader.read()
        if (done) break
        html += decoder.decode(value.subarray(0, HTML_PREFIX_LIMIT - html.length), { stream: true })
      }
    } finally {
      await reader.cancel()
    }

    // Template contents are inert and never enter the chat DOM.
    const template = document.createElement('template')
    template.innerHTML = html
    for (const link of template.content.querySelectorAll<HTMLLinkElement>('link[rel][href]')) {
      if (!/(?:^|\s)(?:icon|apple-touch-icon)(?:\s|$)/i.test(link.rel)) continue
      try {
        const icon = new URL(link.getAttribute('href')!, response.url || origin)
        if (webSourceIconOrigin(icon.href) && !(origin.startsWith('https:') && icon.protocol === 'http:')) return icon.href
      } catch {
        // Continue to the next declared icon.
      }
    }
  } catch {
    // Sites may restrict cross-origin access, or have no usable favicon.
  }
  return null
}

export function discoverWebSourceIcon(origin: string): Promise<string | null> {
  const cached = iconDiscovery.get(origin)
  if (cached) return cached
  const result = readPageIcon(origin)
  if (iconDiscovery.size >= ICON_DISCOVERY_LIMIT) {
    const oldest = iconDiscovery.keys().next().value
    if (oldest) iconDiscovery.delete(oldest)
  }
  iconDiscovery.set(origin, result)
  return result
}
