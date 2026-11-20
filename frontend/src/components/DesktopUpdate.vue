<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

type State = { phase: string; version: string; message: string; session: string; latest?: string; progress?: number }
const state = ref<State>()
const error = ref('')
const busy = ref(false)
let timer: number | undefined
let alive = true
const headers = { 'X-SimpleTavern-Desktop': '1' }
async function refresh() {
  try {
    const response = await fetch('/api/desktop/state', { headers, cache: 'no-store' })
    if (!response.ok) throw new Error()
    state.value = await response.json()
    error.value = ''
  } catch {
    error.value = '正在等待本地服务恢复…'
  }
}
async function poll() {
  await refresh()
  if (alive) timer = window.setTimeout(poll, 1500)
}
async function act(action: string) {
  if (busy.value || !state.value) return
  busy.value = true
  try {
    const response = await fetch('/api/desktop/update/' + action, {
      method: 'POST', headers: { ...headers, 'X-Desktop-Session': state.value.session },
    })
    if (!response.ok) throw new Error()
    await refresh()
  } catch {
    error.value = '操作失败，请重试'
  } finally {
    busy.value = false
  }
}
const action = computed(() => state.value?.phase === 'ready' ? ['restart', '立即重启更新']
  : state.value?.phase === 'waiting' ? ['cancel', '取消重启']
  : state.value?.phase === 'available' ? ['download', '退出时更新'] : ['check', '检查更新'])
onMounted(poll)
onUnmounted(() => { alive = false; window.clearTimeout(timer) })
</script>
<template>
  <div class="settings-group">
    <div class="settings-group-title">桌面版 {{ state?.version }}</div>
    <p class="settings-readout" role="status">{{ error || state?.message || '正在读取版本…' }}</p>
    <button type="button" class="btn btn-sm btn-secondary self-start"
      :disabled="busy || !state || ['checking','downloading','applying'].includes(state.phase)"
      @click="act(action[0]!)">{{ action[1] }}</button>
  </div>
</template>
