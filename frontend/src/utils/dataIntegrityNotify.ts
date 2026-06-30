import type { DataIntegrityIssue } from '../api/dataIntegrity'
import type { DataIntegrityRepairResponse } from '../api/dataIntegrity'

export const ISSUE_CODE_LABELS: Record<string, string> = {
  empty: '空文件',
  all_zero: '全 0 字节',
  invalid_utf8: 'UTF-8 非法',
  invalid_json: 'JSON 非法',
  schema_mismatch: '结构不匹配',
  orphan_reference: '角色缺失',
}

export const ISSUE_KIND_LABELS: Record<string, string> = {
  chat_record: '聊天记录',
  legacy_chat: '旧版聊天',
  chat_memory: '长期记忆',
  assistant_chat_global: '全局助手',
  assistant_chat_workspace: '工作区助手',
  assistant_chat_session: '会话助手',
  settings: '全局设置',
  assistant_settings: '助手设置',
  character_card: '角色卡',
  world_book: '世界书',
}

export function formatIssueLine(issue: DataIntegrityIssue): string {
  const codeLabel = ISSUE_CODE_LABELS[issue.code] ?? issue.code
  const kindLabel = ISSUE_KIND_LABELS[issue.kind] ?? issue.kind
  return `- ${codeLabel}（${kindLabel}）：${issue.path}`
}

export function formatIssueLines(issues: DataIntegrityIssue[], max = 6): string[] {
  const lines = issues.slice(0, max).map(formatIssueLine)
  if (issues.length > max) {
    lines.push(`- 以及另外 ${issues.length - max} 个文件`)
  }
  return lines
}

export function summarizeAutoRepair(autoIssues: DataIntegrityIssue[], manualIssues: DataIntegrityIssue[]): string {
  const parts = [
    '检测到可自动清理的数据异常：',
    '',
    ...formatIssueLines(autoIssues),
    '',
    '是否立即执行一次清理？这会删除损坏的聊天/记忆文件，或将助手记录重置为空 JSON。',
  ]
  if (manualIssues.length > 0) {
    parts.push('')
    parts.push(`另有 ${manualIssues.length} 个设置/角色/世界书/孤儿会话异常需人工检查，不会被自动清理：`)
    parts.push(...formatIssueLines(manualIssues, 4))
  }
  return parts.join('\n')
}

export function summarizeManualOnly(manualIssues: DataIntegrityIssue[]): string {
  return [
    '检测到以下数据文件异常，需人工检查处理（不会自动修改设置/角色/世界书）：',
    '',
    ...formatIssueLines(manualIssues),
  ].join('\n')
}

export function summarizeRepairResult(result: DataIntegrityRepairResponse): string {
  const parts: string[] = []
  if (result.repaired.length > 0) {
    parts.push(`已处理 ${result.repaired.length} 个异常文件。`)
  }
  if (result.skipped.length > 0) {
    parts.push(`跳过 ${result.skipped.length} 个文件，原因通常是文件已变化、已恢复正常或需人工处理。`)
  }
  if (result.hasIssues) {
    parts.push(`仍剩 ${result.remainingIssues.length} 个异常文件，稍后会继续保留在巡检列表中。`)
  }
  if (parts.length === 0) {
    parts.push('本次没有需要处理的异常文件。')
  }
  return parts.join('\n')
}

export function buildIssueFingerprint(issues: DataIntegrityIssue[]): string {
  return issues
    .map((issue) => `${issue.path}:${issue.code}:${issue.mtimeNs}`)
    .sort()
    .join('|')
}

export function partitionRepairableIssues(issues: DataIntegrityIssue[]) {
  return {
    autoIssues: issues.filter((issue) => issue.repairAction !== 'none'),
    manualIssues: issues.filter((issue) => issue.repairAction === 'none'),
  }
}
