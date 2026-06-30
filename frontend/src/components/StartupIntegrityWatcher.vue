<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'
import type { DataIntegrityIssue } from '../api/dataIntegrity'
import { getDataIntegrityIssues, repairDataIntegrity } from '../api/dataIntegrity'
import { notifyConfirm, notifyMessage } from '../composables/useNotify'

const ISSUE_CODE_LABELS: Record<string, string> = {
  empty: '空文件',
  all_zero: '全 0 字节',
  invalid_utf8: 'UTF-8 非法',
  invalid_json: 'JSON 非法',
  schema_mismatch: '结构不匹配',
  orphan_reference: '角色缺失',
}

let timerId: number | null = null
let pollCount = 0
let promptInFlight = false
let lastFingerprint: string | null = null

function buildFingerprint(issues: DataIntegrityIssue[]) {
  return issues
    .map((issue) => `${issue.path}:${issue.code}:${issue.mtimeNs}`)
    .sort()
    .join('|')
}

function formatIssueLines(issues: DataIntegrityIssue[], max = 6) {
  const lines = issues.slice(0, max).map((issue) => {
    const label = ISSUE_CODE_LABELS[issue.code] ?? issue.code
    return `- ${label}：${issue.path}`
  })
  if (issues.length > max) {
    lines.push(`- 以及另外 ${issues.length - max} 个文件`)
  }
  return lines
}

function summarizeAutoRepair(autoIssues: DataIntegrityIssue[], manualIssues: DataIntegrityIssue[]) {
  const parts = [
    '检测到聊天记录或助手记录存在异常文件：',
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

function summarizeManualOnly(manualIssues: DataIntegrityIssue[]) {
  return [
    '检测到以下数据文件异常，需人工检查处理（不会自动修改设置/角色/世界书）：',
    '',
    ...formatIssueLines(manualIssues),
  ].join('\n')
}

function summarizeRepairResult(result: Awaited<ReturnType<typeof repairDataIntegrity>>) {
  const parts: string[] = []
  if (result.repaired.length > 0) {
    parts.push(`已处理 ${result.repaired.length} 个异常文件。`)
  }
  if (result.skipped.length > 0) {
    parts.push(`跳过 ${result.skipped.length} 个文件，原因通常是文件已变化或已恢复正常。`)
  }
  if (result.hasIssues) {
    parts.push(`仍剩 ${result.remainingIssues.length} 个异常文件，稍后会继续保留在巡检列表中。`)
  }
  if (parts.length === 0) {
    parts.push('本次没有需要处理的异常文件。')
  }
  return parts.join('\n')
}

async function pollIssues() {
  try {
    const result = await getDataIntegrityIssues()
    if (!result.hasIssues || result.issues.length === 0) {
      lastFingerprint = null
      return
    }

    const fingerprint = buildFingerprint(result.issues)
    if (promptInFlight || fingerprint === lastFingerprint) {
      return
    }

    lastFingerprint = fingerprint
    promptInFlight = true
    try {
      const autoIssues = result.issues.filter((issue) => issue.repairAction !== 'none')
      const manualIssues = result.issues.filter((issue) => issue.repairAction === 'none')

      if (autoIssues.length === 0) {
        await notifyMessage(summarizeManualOnly(manualIssues), { title: '数据完整性巡检' })
        return
      }

      const confirmed = await notifyConfirm({
        title: '数据完整性巡检',
        message: summarizeAutoRepair(autoIssues, manualIssues),
      })
      if (!confirmed) {
        return
      }

      const repairResult = await repairDataIntegrity(autoIssues.map((issue) => issue.path))
      lastFingerprint = repairResult.hasIssues ? buildFingerprint(repairResult.remainingIssues) : null
      await notifyMessage(summarizeRepairResult(repairResult), { title: '数据完整性巡检' })
    } catch (error) {
      await notifyMessage(`修复异常文件失败：${error instanceof Error ? error.message : String(error)}`, {
        title: '数据完整性巡检',
      })
    } finally {
      promptInFlight = false
    }
  } catch (error) {
    console.debug('[data-integrity] poll issues failed', error)
  }
}

function scheduleNextPoll(delayMs: number) {
  timerId = window.setTimeout(async () => {
    await pollIssues()
    pollCount += 1
    scheduleNextPoll(pollCount < 4 ? 15000 : 60000)
  }, delayMs)
}

onMounted(() => {
  void pollIssues()
  scheduleNextPoll(15000)
})

onBeforeUnmount(() => {
  if (timerId !== null) {
    window.clearTimeout(timerId)
    timerId = null
  }
})
</script>

<template></template>