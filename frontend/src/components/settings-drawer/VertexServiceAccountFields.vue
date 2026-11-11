<script setup lang="ts">
/**
 * Vertex 服务账号：导入 Google Cloud 下载的密钥 JSON，拆成邮箱、私钥、项目 ID、位置四项显示。
 *
 * 存储不变：整段 JSON 仍放在连接的 apiKey 里（后端读设置时把 private_key 换成占位内容，写回时还原），
 * 项目 ID 和位置放在 providerParams 里，由后端填进地址模板。这里只负责导入、展示和改这两个参数。
 * 位置不在 JSON 里，必须由用户填。
 */
import { computed, ref } from 'vue'
import { FileJson, RefreshCw } from 'lucide-vue-next'
import SettingsField from './SettingsField.vue'

/** 后端隐去私钥时写入的占位内容（backend/app/llm/vertex_auth.py 的 REDACTED_PRIVATE_KEY） */
const REDACTED_PRIVATE_KEY = '__simpletavern_private_key_hidden__'

interface VertexConnectionLike {
  apiKey: string
  baseUrl?: string | null
  providerParams?: Record<string, string> | null
}

const props = defineProps<{
  connection: VertexConnectionLike
}>()

const fileInputRef = ref<HTMLInputElement | null>(null)
const pasteText = ref('')
const importError = ref('')
/** 已有账号时点「更换」才回到导入界面；导入成功前旧账号不动 */
const replacing = ref(false)

interface ParsedAccount {
  clientEmail: string
  projectId: string
  privateKeyId: string
  keyHidden: boolean
}

function readAccount(text: string): { account: ParsedAccount | null; error: string } {
  const raw = (text || '').trim()
  if (!raw) return { account: null, error: '' }
  let data: unknown
  try {
    data = JSON.parse(raw)
  } catch {
    return { account: null, error: '不是合法的 JSON。请导入从 Google Cloud 下载的服务账号密钥文件。' }
  }
  if (!data || typeof data !== 'object' || Array.isArray(data)) {
    return { account: null, error: 'JSON 应该是一个对象。' }
  }
  const obj = data as Record<string, unknown>
  if (obj.type !== 'service_account') {
    return { account: null, error: 'type 不是 service_account，这不是服务账号密钥。' }
  }
  const missing = ['client_email', 'private_key', 'token_uri'].filter((k) => typeof obj[k] !== 'string' || !(obj[k] as string).trim())
  if (missing.length) {
    return { account: null, error: `缺少字段：${missing.join('、')}` }
  }
  return {
    account: {
      clientEmail: String(obj.client_email).trim(),
      projectId: typeof obj.project_id === 'string' ? obj.project_id.trim() : '',
      privateKeyId: typeof obj.private_key_id === 'string' ? obj.private_key_id.trim() : '',
      keyHidden: obj.private_key === REDACTED_PRIVATE_KEY,
    },
    error: '',
  }
}

const current = computed(() => readAccount(props.connection.apiKey))
const account = computed(() => current.value.account)
const showImport = computed(() => !account.value || replacing.value)

const privateKeyText = computed(() => {
  const a = account.value
  if (!a) return ''
  const id = a.privateKeyId ? `，密钥 ID ${a.privateKeyId.slice(0, 8)}…` : ''
  return a.keyHidden ? `已保存，不再显示${id}` : `已导入，保存后不再显示${id}`
})

/** 地址模板里有这个占位符时，这个参数才起作用 */
function templateUses(key: string): boolean {
  return (props.connection.baseUrl || '').includes(`{${key}}`)
}
const usesProject = computed(() => templateUses('project'))
const usesLocation = computed(() => templateUses('location'))

function paramValue(key: string): string {
  return props.connection.providerParams?.[key] ?? ''
}
function setParam(key: string, value: string) {
  props.connection.providerParams = { ...(props.connection.providerParams ?? {}), [key]: value }
}

function importText(text: string) {
  const result = readAccount(text)
  if (!result.account) {
    importError.value = result.error || '内容是空的。'
    return
  }
  if (result.account.keyHidden) {
    importError.value = '这份 JSON 里的私钥已经被隐去，请导入原始的密钥文件。'
    return
  }
  importError.value = ''
  pasteText.value = ''
  replacing.value = false
  props.connection.apiKey = text.trim()
  // 项目 ID 跟着新账号走；位置不在 JSON 里，保留用户填的
  if (result.account.projectId) setParam('project', result.account.projectId)
}

async function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  try {
    importText(await file.text())
  } catch {
    importError.value = '读不了这个文件。'
  }
}

function onPasteInput() {
  const text = pasteText.value.trim()
  if (!text) {
    importError.value = ''
    return
  }
  // 粘贴的是完整 JSON 时直接导入；还没粘完（解析不了）就先不报错，等失焦再说
  if (readAccount(text).account) importText(text)
}

function cancelReplace() {
  replacing.value = false
  pasteText.value = ''
  importError.value = ''
}
</script>

<template>
  <div class="settings-field" data-vertex-service-account>
    <input ref="fileInputRef" type="file" accept=".json,application/json" class="hidden" @change="onFileChange" />

    <template v-if="showImport">
      <SettingsField
        label="服务账号密钥"
        more="在 Google Cloud 控制台的「IAM 和管理 → 服务账号 → 密钥」里创建并下载 JSON 密钥，账号需要 Vertex AI User 角色。私钥只保存在本机，用来换取短期 access token；设置备份不含私钥，恢复备份后要重新导入。"
      >
        <template #actions>
          <button v-if="replacing" type="button" class="btn btn-xs btn-secondary" @click="cancelReplace">取消</button>
        </template>
        <div class="flex flex-col gap-2">
          <button type="button" class="btn btn-secondary w-full justify-center" @click="fileInputRef?.click()">
            <FileJson class="h-4 w-4" />
            导入 JSON 文件
          </button>
          <textarea
            v-model="pasteText"
            rows="3"
            class="input textarea w-full resize-y font-mono text-xs"
            spellcheck="false"
            autocomplete="off"
            aria-label="粘贴服务账号 JSON"
            placeholder="或者把 JSON 全文粘贴到这里"
            @input="onPasteInput"
            @blur="pasteText.trim() && importText(pasteText)"
          ></textarea>
        </div>
      </SettingsField>
      <p v-if="importError || (!replacing && current.error)" class="settings-hint text-error" role="alert">
        {{ importError || current.error }}
      </p>
    </template>

    <template v-else-if="account">
      <SettingsField label="服务账号邮箱">
        <template #actions>
          <button type="button" class="btn btn-xs btn-secondary" @click="replacing = true">
            <RefreshCw class="h-3 w-3" />
            更换
          </button>
        </template>
        <input :value="account.clientEmail" type="text" class="input w-full" readonly aria-label="服务账号邮箱" />
      </SettingsField>
      <SettingsField label="私钥">
        <input :value="privateKeyText" type="text" class="input w-full" readonly aria-label="私钥" />
      </SettingsField>
      <div class="grid gap-3 sm:grid-cols-2">
        <SettingsField v-if="usesProject" label="项目 ID" more="默认取密钥文件里的 project_id。要调用另一个项目时可以改。">
          <input
            :value="paramValue('project')"
            type="text"
            class="input w-full"
            placeholder="my-gcp-project"
            aria-label="项目 ID"
            @input="setParam('project', ($event.target as HTMLInputElement).value)"
          />
        </SettingsField>
        <SettingsField
          v-if="usesLocation"
          label="位置"
          :hint="paramValue('location').trim() ? undefined : '必填，密钥文件里没有这一项。'"
          more="global，或具体区域如 asia-southeast1、us-central1。不同区域可用的模型不一样。"
        >
          <input
            :value="paramValue('location')"
            type="text"
            class="input w-full"
            placeholder="global"
            aria-label="位置"
            @input="setParam('location', ($event.target as HTMLInputElement).value)"
          />
        </SettingsField>
      </div>
    </template>
  </div>
</template>
