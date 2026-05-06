import { useCharactersStore, useChatsStore, useSettingsStore } from '../stores'
import type { MvuMode } from '../types/models'

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

export interface SillyTavernConfirmOptions {
  pendingId: string
  enableMvuCompatibility: boolean
  mvuMode: MvuMode
}

export interface SillyTavernMvuCompatResult {
  mode: MvuMode
  applied: boolean
  summary?: string
  rules?: number
  warnings?: string[]
  worldbookMarks?: Array<Record<string, unknown>>
  confidence?: number
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

  async function refreshDataAfterImport() {
    await settingsStore.load()
    await charactersStore.loadAll()
    await chatsStore.loadGroupList()
    if (chatsStore.characterId) {
      await chatsStore.loadList(chatsStore.characterId)
    }
  }

  function formatImportResultMessage(result: SettingsImportResult) {
    const imported = (result.imported || []).join(', ') || '无'
    const compat = result.mvuCompat
    const rulesSummary = typeof compat?.rules === 'number' ? `生成 regex 规则 ${compat.rules} 条。` : ''
    const mvuSummaryText = compat?.summary || rulesSummary
    const mvuSummary = compat
      ? `\nMVU 兼容：${compat.mode} / ${compat.applied ? '已应用' : '未应用'}${mvuSummaryText ? `，${mvuSummaryText}` : ''}`
      : ''
    const warnings = result.warnings?.length ? `\n警告：${result.warnings.join('; ')}` : ''
    const mvuWarnings = !warnings && compat?.warnings?.length ? `\nMVU 警告：${compat.warnings.join('; ')}` : ''
    return `导入完成：${imported}${mvuSummary}${warnings}${mvuWarnings}`
  }

  return {
    importSettingsFile,
    previewSillyTavernImport,
    confirmSillyTavernImport,
    refreshDataAfterImport,
    formatImportResultMessage,
  }
}
