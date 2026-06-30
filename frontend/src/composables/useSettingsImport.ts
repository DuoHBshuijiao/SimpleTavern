import { useCharactersStore, useChatsStore, useSettingsStore } from '../stores'
import type { MvuMode } from '../types/models'

export interface SillyTavernMvuCompatResult {
  mode: MvuMode
  applied: boolean
  summary?: string
  rules?: number
  warnings?: string[]
  worldbookMarks?: Array<Record<string, unknown>>
  confidence?: number
}

export interface SettingsImportResult {
  ok?: boolean
  imported?: string[]
  warnings?: string[]
  mvuCompat?: SillyTavernMvuCompatResult
}

export interface SillyTavernMvuPreview {
  hasTavernHelper: boolean
  hasRegexScripts: boolean
  regexScriptCount: number
  characterBookCandidateCount: number
  characterBookCandidates: Array<{
    title: string
    enabled: boolean
    keys: string[]
  }>
  suggestedMode: MvuMode
}

export interface SillyTavernImportPreview {
  characterName: string
  worldBookName: string
  worldBookEntryCount: number
  mvu: SillyTavernMvuPreview
}

export interface SillyTavernPreviewResult {
  ok: boolean
  pendingId: string
  expiresAt: string
  preview: SillyTavernImportPreview
}

export interface SillyTavernConfirmResult extends SettingsImportResult {
  character?: unknown
  worldbook?: unknown
  mvu?: {
    enabled: boolean
    requestedMode: MvuMode
    detected: SillyTavernMvuPreview
  }
}

export interface SillyTavernConfirmOptions {
  pendingId: string
  enableMvuCompatibility: boolean
  mvuMode: MvuMode
}

/** 与 confirm 相同字段 + 可选头像文件名（已由 /api/avatars 保存时使用） */
export interface SillyTavernMaterializeOptions extends SillyTavernConfirmOptions {
  avatarFilename?: string | null
}

export interface SillyTavernMaterializeResult {
  ok: boolean
  character: Record<string, unknown>
  worldbook?: Record<string, unknown> | null
  warnings?: string[]
  mvuCompat?: SillyTavernMvuCompatResult
  mvu?: SillyTavernConfirmResult['mvu']
}

export function normalizeImportNoticeText(text: string): string {
  return text.replace(/L4\s*暂不生成\s*regex\s*模式规则；?/g, '未生成正文正则规则；')
}

export function formatImportResultMessage(result: SettingsImportResult): string {
  const imported = (result.imported || []).join(', ') || '无'
  const compat = result.mvuCompat
  const rulesSummary = typeof compat?.rules === 'number' ? `生成 regex 规则 ${compat.rules} 条。` : ''
  const mvuSummaryText = compat?.summary || rulesSummary
  const mvuSummary = compat
    ? `\nMVU 兼容：${compat.mode} / ${compat.applied ? '已应用' : '未应用'}${mvuSummaryText ? `，${mvuSummaryText}` : ''}`
    : ''
  const warnings = result.warnings?.length
    ? `\n警告：${result.warnings.map(normalizeImportNoticeText).join('; ')}`
    : ''
  // 顶层 warnings 与 MVU 兼容 warnings 同时存在时都要展示，避免互斥丢失任一来源。
  const mvuWarnings = compat?.warnings?.length
    ? `\nMVU 警告：${compat.warnings.map(normalizeImportNoticeText).join('; ')}`
    : ''
  return `导入完成：${imported}${mvuSummary}${warnings}${mvuWarnings}`
}

export function useSettingsImport() {
  const settingsStore = useSettingsStore()
  const chatsStore = useChatsStore()
  const charactersStore = useCharactersStore()

  async function importSettingsFile(file: File): Promise<SettingsImportResult> {
    const fd = new FormData()
    fd.append('file', file)
    const r = await fetch('/api/import', { method: 'POST', body: fd })
    if (!r.ok) {
      throw new Error(await r.text())
    }
    return (await r.json()) as SettingsImportResult
  }

  async function previewSillyTavernImport(file: File): Promise<SillyTavernPreviewResult> {
    const fd = new FormData()
    fd.append('file', file)
    const r = await fetch('/api/import/sillytavern/preview', { method: 'POST', body: fd })
    if (!r.ok) {
      throw new Error(await r.text())
    }
    return (await r.json()) as SillyTavernPreviewResult
  }

  async function confirmSillyTavernImport(options: SillyTavernConfirmOptions): Promise<SillyTavernConfirmResult> {
    const r = await fetch('/api/import/sillytavern/confirm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(options),
    })
    if (!r.ok) {
      throw new Error(await r.text())
    }
    return (await r.json()) as SillyTavernConfirmResult
  }

  async function materializeSillyTavernPending(options: SillyTavernMaterializeOptions): Promise<SillyTavernMaterializeResult> {
    const r = await fetch('/api/import/sillytavern/materialize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        pendingId: options.pendingId,
        enableMvuCompatibility: options.enableMvuCompatibility,
        mvuMode: options.mvuMode,
        avatarFilename: options.avatarFilename ?? null,
      }),
    })
    if (!r.ok) {
      throw new Error(await r.text())
    }
    return (await r.json()) as SillyTavernMaterializeResult
  }

  async function refreshDataAfterImport() {
    await settingsStore.load()
    await charactersStore.loadAll()
    await chatsStore.loadGroupList()
    if (chatsStore.characterId) {
      await chatsStore.loadList(chatsStore.characterId)
    }
  }

  return {
    importSettingsFile,
    previewSillyTavernImport,
    confirmSillyTavernImport,
    materializeSillyTavernPending,
    refreshDataAfterImport,
    formatImportResultMessage,
  }
}
