import { apiDelete, apiGet, apiPost, apiPut } from './http'

export type UpdateCheckResponse = {
  currentVersion: string
  latestVersion: string | null
  hasUpdate: boolean
  tagName: string | null
  zipUrl: string | null
  releaseNotes: string | null
}

export type StartupUpdateCheckResponse = UpdateCheckResponse & {
  ignoredReleaseTag: string | null
  shouldNotify: boolean
}

export function getManualUpdateCheck() {
  return apiGet<UpdateCheckResponse>('/api/update/check')
}

export function getStartupUpdateCheck() {
  return apiGet<StartupUpdateCheckResponse>('/api/update/startup-check')
}

export function downloadUpdate(tagName: string) {
  return apiPost<{ ok: boolean; path: string }>('/api/update/download', { tagName })
}

export function runUpdate() {
  return apiPost<{ ok: boolean }>('/api/update/run', {})
}

export function setIgnoredUpdateTag(tag: string) {
  return apiPut<{ ignoredReleaseTag: string | null }>('/api/update/ignored-tag', { tag })
}

export function clearIgnoredUpdateTag() {
  return apiDelete('/api/update/ignored-tag')
}