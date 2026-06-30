<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'
import { getDataIntegrityIssues, repairDataIntegrity } from '../api/dataIntegrity'
import { notifyConfirm, notifyMessage } from '../composables/useNotify'
import {
  buildIssueFingerprint,
  partitionRepairableIssues,
  summarizeAutoRepair,
  summarizeManualOnly,
  summarizeRepairResult,
} from '../utils/dataIntegrityNotify'

let timerId: number | null = null
let pollCount = 0
let promptInFlight = false
let lastFingerprint: string | null = null

async function pollIssues() {
  try {
    const result = await getDataIntegrityIssues()
    if (!result.hasIssues || result.issues.length === 0) {
      lastFingerprint = null
      return
    }

    const fingerprint = buildIssueFingerprint(result.issues)
    if (promptInFlight || fingerprint === lastFingerprint) {
      return
    }

    lastFingerprint = fingerprint
    promptInFlight = true
    try {
      const { autoIssues, manualIssues } = partitionRepairableIssues(result.issues)

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
      lastFingerprint = repairResult.hasIssues ? buildIssueFingerprint(repairResult.remainingIssues) : null
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
