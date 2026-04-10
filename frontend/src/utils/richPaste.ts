import { apiPost } from '../api/http'

export type RichPasteResolution = {
  text: string
  files: File[]
}

function extractFilesFromClipboard(clipboardData: DataTransfer): File[] {
  const files: File[] = []
  for (const item of Array.from(clipboardData.items || [])) {
    if (item.kind !== 'file') continue
    const file = item.getAsFile()
    if (file) files.push(file)
  }
  if (files.length > 0) return files
  return Array.from(clipboardData.files || [])
}

function extractImageFilesFromHtml(html: string): File[] {
  const files: File[] = []
  const dataUrlRe = /<img[^>]+src\s*=\s*["'](data:image\/(\w+);base64,([^"']+))["']/gi
  let match: RegExpExecArray | null
  while ((match = dataUrlRe.exec(html)) !== null) {
    const mimeSubtype = match[2]
    const base64 = match[3]
    if (!mimeSubtype || !base64) continue
    const subtype = mimeSubtype.toLowerCase()
    const mimeType = `image/${subtype}`
    try {
      const binary = atob(base64)
      const bytes = new Uint8Array(binary.length)
      for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index)
      const blob = new Blob([bytes], { type: mimeType })
      const ext = subtype === 'jpeg' || subtype === 'jpg' ? 'jpg' : subtype
      files.push(new File([blob], `pasted.${ext}`, { type: mimeType }))
    } catch {
      // 忽略单张解析失败
    }
  }
  return files
}

function stripHtmlToText(html: string): string {
  const doc = new DOMParser().parseFromString(html, 'text/html')
  return (doc.body?.textContent ?? '').trim()
}

function base64ToFile(base64: string, mimeType: string, name: string): File {
  const binary = atob(base64)
  const bytes = new Uint8Array(binary.length)
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index)
  return new File([bytes], name || 'pasted.png', { type: mimeType })
}

export async function resolveRichPaste(clipboardData: DataTransfer | null): Promise<RichPasteResolution | null> {
  if (!clipboardData) return null

  const filesFromClipboard = extractFilesFromClipboard(clipboardData)
  const plainText = clipboardData.getData('text/plain')
  const htmlText = clipboardData.getData('text/html')
  const hasHtml = Boolean(htmlText)

  if (filesFromClipboard.length > 0 && !hasHtml) {
    return {
      text: plainText,
      files: filesFromClipboard,
    }
  }

  if (!hasHtml) {
    return {
      text: plainText,
      files: filesFromClipboard,
    }
  }

  const hasFileUrls = /file:\/\//i.test(htmlText)
  if (hasFileUrls) {
    try {
      const res = await apiPost<{ text: string; images: { base64: string; mimeType: string; name: string }[] }>(
        '/api/clipboard/resolve-rich-paste',
        { text: plainText, html: htmlText },
      )
      const files = [
        ...filesFromClipboard,
        ...(res.images || []).map((image) => base64ToFile(image.base64, image.mimeType, image.name)),
      ]
      return {
        text: res.text || plainText || stripHtmlToText(htmlText),
        files,
      }
    } catch {
      // 回退到本地解析
    }
  }

  return {
    text: plainText || stripHtmlToText(htmlText),
    files: [...filesFromClipboard, ...extractImageFilesFromHtml(htmlText)],
  }
}
