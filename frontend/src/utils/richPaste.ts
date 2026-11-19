export type RichPasteResolution = {
  text: string
  files: File[]
  requiresFileSelection?: boolean
}

export const FILE_ONLY_PASTE_MESSAGE = '剪贴板只提供了图片的本机路径。请用附件按钮选择该图片。'

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

function extractEmbeddedImages(sources: string[]): File[] {
  const files: File[] = []
  for (const source of sources) {
    const match = /^data:image\/(\w+);base64,(.+)$/is.exec(source)
    const mimeSubtype = match?.[1]
    const base64 = match?.[2]
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

export function resolveRichPaste(clipboardData: DataTransfer | null): RichPasteResolution | null {
  if (!clipboardData) return null

  const filesFromClipboard = extractFilesFromClipboard(clipboardData)
  const plainText = clipboardData.getData('text/plain')
  const htmlText = clipboardData.getData('text/html')
  if (!htmlText) {
    return {
      text: plainText,
      files: filesFromClipboard,
    }
  }

  const template = document.createElement('template')
  template.innerHTML = htmlText
  const sources = Array.from(template.content.querySelectorAll('img[src]'), (image) => image.getAttribute('src') || '')
  const files = [...filesFromClipboard, ...extractEmbeddedImages(sources)]
  return {
    text: plainText || (template.content.textContent ?? '').trim(),
    files,
    requiresFileSelection: files.length === 0 && sources.some((source) => /^file:\/\//i.test(source)),
  }
}
