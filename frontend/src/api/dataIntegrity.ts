import { apiGet, apiPost } from './http'

export type DataIntegrityIssueCode = 'empty' | 'all_zero' | 'invalid_utf8' | 'invalid_json' | 'schema_mismatch'
export type DataIntegrityRepairAction = 'delete' | 'reset_json'

export type DataIntegrityIssue = {
  path: string
  kind: string
  code: DataIntegrityIssueCode
  message: string
  detail: string | null
  size: number
  mtimeNs: number
  discoveredAt: string
  repairAction: DataIntegrityRepairAction
}

export type DataIntegrityIssuesResponse = {
  hasIssues: boolean
  issues: DataIntegrityIssue[]
}

export type DataIntegrityRepairResult = {
  path: string
  status: 'repaired' | 'skipped'
  reason?: string
  action?: DataIntegrityRepairAction
}

export type DataIntegrityRepairResponse = {
  requested: number
  repaired: DataIntegrityRepairResult[]
  skipped: DataIntegrityRepairResult[]
  hasIssues: boolean
  remainingIssues: DataIntegrityIssue[]
}

export function getDataIntegrityIssues() {
  return apiGet<DataIntegrityIssuesResponse>('/api/data-integrity/issues')
}

export function repairDataIntegrity(paths?: string[]) {
  return apiPost<DataIntegrityRepairResponse>('/api/data-integrity/repair', {
    paths: paths ?? [],
  })
}