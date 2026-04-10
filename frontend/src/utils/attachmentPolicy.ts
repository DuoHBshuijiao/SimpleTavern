import type { AssistantAttachmentKind } from '../types/models'

export const ASSISTANT_TEXT_ATTACHMENT_MAX_BYTES = 2 * 1024 * 1024
export const ASSISTANT_IMAGE_ATTACHMENT_MAX_BYTES = 100 * 1024 * 1024
export const MAIN_CHAT_IMAGES_ONLY = true

export type AttachmentPolicyTarget = 'main-chat' | 'assistant'
export type AttachmentRejectReason = 'unsupported' | 'too-large'

export type AttachmentValidationResult = {
  accepted: Array<{ file: File; kind: AssistantAttachmentKind }>
  rejected: Array<{ file: File; reason: AttachmentRejectReason; kind?: AssistantAttachmentKind | null }>
}

const ASSISTANT_TEXT_EXTENSIONS = new Set(['.txt', '.json', '.xml'])
const ASSISTANT_TEXT_MIME_TYPES = new Set([
  'text/plain',
  'text/json',
  'text/xml',
  'application/json',
  'application/xml',
])

export function normalizeMimeType(mimeType: string | null | undefined): string {
  return (mimeType || '').split(';', 1)[0]!.trim().toLowerCase()
}

export function isImageMimeType(mimeType: string | null | undefined): boolean {
  return normalizeMimeType(mimeType).startsWith('image/')
}

export function classifyAssistantFile(file: File): AssistantAttachmentKind | null {
  const mimeType = normalizeMimeType(file.type)
  const lowerName = file.name.toLowerCase()
  const suffix = lowerName.includes('.') ? lowerName.slice(lowerName.lastIndexOf('.')) : ''
  if (isImageMimeType(mimeType)) return 'image'
  if (ASSISTANT_TEXT_EXTENSIONS.has(suffix)) return 'text'
  if (ASSISTANT_TEXT_MIME_TYPES.has(mimeType)) return 'text'
  if (mimeType.startsWith('text/')) return 'text'
  if (mimeType.endsWith('+json') || mimeType.endsWith('+xml')) return 'text'
  return null
}

export function validateFilesForTarget(files: File[], target: AttachmentPolicyTarget): AttachmentValidationResult {
  const accepted: Array<{ file: File; kind: AssistantAttachmentKind }> = []
  const rejected: Array<{ file: File; reason: AttachmentRejectReason; kind?: AssistantAttachmentKind | null }> = []

  for (const file of files) {
    if (target === 'main-chat') {
      if (!isImageMimeType(file.type)) {
        rejected.push({ file, reason: 'unsupported', kind: null })
        continue
      }
      if (file.size > ASSISTANT_IMAGE_ATTACHMENT_MAX_BYTES) {
        rejected.push({ file, reason: 'too-large', kind: 'image' })
        continue
      }
      accepted.push({ file, kind: 'image' })
      continue
    }

    const kind = classifyAssistantFile(file)
    if (!kind) {
      rejected.push({ file, reason: 'unsupported', kind: null })
      continue
    }
    const sizeLimit = kind === 'image' ? ASSISTANT_IMAGE_ATTACHMENT_MAX_BYTES : ASSISTANT_TEXT_ATTACHMENT_MAX_BYTES
    if (file.size > sizeLimit) {
      rejected.push({ file, reason: 'too-large', kind })
      continue
    }
    accepted.push({ file, kind })
  }

  return { accepted, rejected }
}

export function formatAttachmentLimit(kind: AssistantAttachmentKind): string {
  return kind === 'image' ? '100MB' : '2MB'
}
