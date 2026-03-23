import { useCharactersStore, useChatsStore, useSettingsStore } from '../stores'

export interface SettingsImportResult {
  ok?: boolean
  imported?: string[]
  warnings?: string[]
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
    const warnings = result.warnings?.length ? `\n警告：${result.warnings.join('; ')}` : ''
    return `导入完成：${imported}${warnings}`
  }

  return {
    importSettingsFile,
    refreshDataAfterImport,
    formatImportResultMessage,
  }
}
