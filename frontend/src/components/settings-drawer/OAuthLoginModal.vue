<script setup lang="ts">
/**
 * GitHub Copilot / OpenAI Codex 登录向导（T-830）。
 * Copilot：设备码。Codex：默认设备码，可选粘贴 PKCE 回调 URL。
 */
import { computed, ref, watch } from 'vue'
import { ExternalLink, Loader2, X } from 'lucide-vue-next'
import {
  cancelOAuthLogin,
  completeOAuthPkce,
  pollOAuthLogin,
  startOAuthLogin,
} from '../../api/llm'
import { useDialogBehavior } from '../../composables/useDialogBehavior'
import { dialogAria } from '../../utils/uiPrimitives'

const props = defineProps<{
  show: boolean
  presetId: string | null
  providerId: string | null
  providerLabel: string
}>()

const emit = defineEmits<{
  close: []
  'logged-in': []
}>()

const titleId = 'oauth-login-title'
const dialogAttrs = dialogAria(titleId)
const { dialogRef } = useDialogBehavior(
  () => props.show,
  () => void close(),
)
void dialogRef

const isCopilot = computed(() => (props.providerId || '').includes('copilot'))
const method = ref<'device_code' | 'pkce'>('device_code')
const enterpriseUrl = ref('')
const starting = ref(false)
const polling = ref(false)
const submitting = ref(false)
const errorText = ref('')
const sessionId = ref('')
const userCode = ref('')
const verificationUri = ref('')
const authorizeUrl = ref('')
const callbackText = ref('')
const copied = ref(false)

let pollTimer: ReturnType<typeof setTimeout> | null = null
let pollGeneration = 0

function resetFlow() {
  pollGeneration += 1
  if (pollTimer) {
    clearTimeout(pollTimer)
    pollTimer = null
  }
  starting.value = false
  polling.value = false
  submitting.value = false
  errorText.value = ''
  sessionId.value = ''
  userCode.value = ''
  verificationUri.value = ''
  authorizeUrl.value = ''
  callbackText.value = ''
  copied.value = false
}

watch(
  () => [props.show, props.presetId, props.providerId] as const,
  ([show]) => {
    if (show) {
      method.value = 'device_code'
      enterpriseUrl.value = ''
      resetFlow()
    } else {
      void abortSession()
    }
  },
)

async function abortSession() {
  const sid = sessionId.value
  pollGeneration += 1
  if (pollTimer) {
    clearTimeout(pollTimer)
    pollTimer = null
  }
  polling.value = false
  if (sid) {
    try {
      await cancelOAuthLogin(sid)
    } catch {
      /* ignore */
    }
  }
}

async function close() {
  await abortSession()
  emit('close')
}

async function copyUserCode() {
  if (!userCode.value) return
  try {
    await navigator.clipboard.writeText(userCode.value)
    copied.value = true
  } catch {
    copied.value = false
  }
}

async function start() {
  if (!props.presetId || starting.value) return
  starting.value = true
  errorText.value = ''
  try {
    const res = await startOAuthLogin({
      presetId: props.presetId,
      providerId: props.providerId,
      method: isCopilot.value ? 'device_code' : method.value,
      enterpriseUrl: isCopilot.value ? enterpriseUrl.value.trim() || null : null,
    })
    sessionId.value = res.sessionId
    userCode.value = res.userCode || ''
    verificationUri.value = res.verificationUri || ''
    authorizeUrl.value = res.authorizeUrl || ''
    if (res.method === 'device_code') {
      polling.value = true
      void pollLoop(res.sessionId, Number(res.interval) || 5)
    }
  } catch (e) {
    errorText.value = e instanceof Error ? e.message : String(e)
  } finally {
    starting.value = false
  }
}

async function pollLoop(sid: string, intervalSec: number) {
  const gen = pollGeneration
  let wait = Math.max(2, intervalSec)
  while (polling.value && gen === pollGeneration) {
    await new Promise((r) => {
      pollTimer = setTimeout(r, wait * 1000)
    })
    if (!polling.value || gen !== pollGeneration) return
    try {
      const res = await pollOAuthLogin(sid)
      if (res.status === 'complete') {
        polling.value = false
        emit('logged-in')
        emit('close')
        return
      }
      if (res.status === 'slow_down') {
        wait = Math.max(wait + 5, Number(res.intervalSeconds) || wait)
        continue
      }
      if (res.status === 'pending') continue
      polling.value = false
      errorText.value = res.message || '登录失败'
      return
    } catch (e) {
      polling.value = false
      errorText.value = e instanceof Error ? e.message : String(e)
      return
    }
  }
}

async function submitPkce() {
  if (!sessionId.value || submitting.value) return
  submitting.value = true
  errorText.value = ''
  try {
    const res = await completeOAuthPkce(sessionId.value, callbackText.value)
    if (res.status === 'complete') {
      emit('logged-in')
      emit('close')
      return
    }
    errorText.value = res.message || '登录失败'
  } catch (e) {
    errorText.value = e instanceof Error ? e.message : String(e)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div v-if="show" class="modal">
    <div class="modal-backdrop" @click="close"></div>
    <div ref="dialogRef" v-bind="dialogAttrs" tabindex="-1" class="modal-content modal-surface chat-modal-width-520-92">
      <div class="modal-header">
        <h3 :id="titleId" class="modal-title">登录 {{ providerLabel }}</h3>
        <button type="button" class="modal-close" aria-label="关闭登录弹窗" @click="close">
          <X class="h-5 w-5" />
        </button>
      </div>
      <div class="modal-body space-y-4">
        <p class="text-sm text-[var(--color-text-muted)]">
          凭证只保存在本机数据目录，不会写进设置备份里的 API Key 字段。
        </p>

        <div v-if="isCopilot && !sessionId" class="form-group">
          <label class="label">GitHub Enterprise 域名（可选）</label>
          <input v-model="enterpriseUrl" class="input w-full" placeholder="github.com" />
        </div>

        <div v-if="!isCopilot && !sessionId" class="form-group space-y-2">
          <label class="label">登录方式</label>
          <div class="flex flex-wrap gap-2">
            <button
              type="button"
              class="btn btn-sm"
              :class="method === 'device_code' ? 'btn-primary' : 'btn-secondary'"
              @click="method = 'device_code'"
            >
              设备码
            </button>
            <button
              type="button"
              class="btn btn-sm"
              :class="method === 'pkce' ? 'btn-primary' : 'btn-secondary'"
              @click="method = 'pkce'"
            >
              浏览器粘贴回调
            </button>
          </div>
        </div>

        <p v-if="errorText" class="text-sm text-error">{{ errorText }}</p>

        <div v-if="userCode" class="space-y-2 rounded-lg border border-[var(--color-border-subtle)] p-3">
          <div class="text-xs text-[var(--color-text-muted)]">在打开的页面输入此代码</div>
          <div class="flex items-center gap-2">
            <code class="text-lg font-semibold tracking-widest text-primary">{{ userCode }}</code>
            <button type="button" class="btn btn-xs btn-secondary" @click="copyUserCode">
              {{ copied ? '已复制' : '复制' }}
            </button>
          </div>
          <a
            v-if="verificationUri"
            :href="verificationUri"
            target="_blank"
            rel="noopener noreferrer"
            class="inline-flex items-center gap-1 text-sm text-brand hover:underline"
          >
            打开验证页面 <ExternalLink class="h-3.5 w-3.5" />
          </a>
          <p v-if="polling" class="flex items-center gap-2 text-xs text-[var(--color-text-muted)]">
            <Loader2 class="h-3.5 w-3.5 animate-spin" /> 等待你在浏览器里确认…
          </p>
        </div>

        <div v-if="authorizeUrl" class="space-y-2">
          <a
            :href="authorizeUrl"
            target="_blank"
            rel="noopener noreferrer"
            class="inline-flex items-center gap-1 text-sm text-brand hover:underline"
          >
            打开 ChatGPT 授权页 <ExternalLink class="h-3.5 w-3.5" />
          </a>
          <p class="text-xs text-[var(--color-text-muted)]">
            浏览器会跳到 localhost:1455（页面打不开也没关系），把地址栏完整 URL 粘贴到下面。
          </p>
          <textarea
            v-model="callbackText"
            class="input w-full min-h-24"
            placeholder="http://localhost:1455/auth/callback?code=…&state=…"
          />
        </div>
      </div>
      <div class="modal-footer">
        <button type="button" class="btn btn-secondary" @click="close">取消</button>
        <button
          v-if="!sessionId"
          type="button"
          class="btn btn-primary"
          :disabled="starting || !presetId"
          @click="start"
        >
          <Loader2 v-if="starting" class="mr-1 h-4 w-4 animate-spin" />
          开始登录
        </button>
        <button
          v-else-if="authorizeUrl"
          type="button"
          class="btn btn-primary"
          :disabled="submitting || !callbackText.trim()"
          @click="submitPkce"
        >
          <Loader2 v-if="submitting" class="mr-1 h-4 w-4 animate-spin" />
          完成登录
        </button>
      </div>
    </div>
  </div>
</template>
