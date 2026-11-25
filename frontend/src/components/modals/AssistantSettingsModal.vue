<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { X } from 'lucide-vue-next'
import ModernSelect from '../ModernSelect.vue'
import ReasoningEffortSegments from '../chat/ReasoningEffortSegments.vue'
import SettingsField from '../settings-drawer/SettingsField.vue'
import SettingsSwitch from '../settings-drawer/SettingsSwitch.vue'
import type { AssistantSettings } from '../../composables/useAssistant'
import { useDialogBehavior } from '../../composables/useDialogBehavior'
import { useProtocolPreview } from '../../composables/useProtocolPreview'
import { dialogAria } from '../../utils/uiPrimitives'
import { resolveModelConnection } from '../../utils/chatGenerationSettings'
import { REASONING_EFFORT_SHORT_LABELS, REASONING_EFFORT_VALUES, normalizeReasoningEffort,
  type ReasoningEffort, type Settings } from '../../types/models'
import type { ResolvePreviewRequest } from '../../api/llm'

const props = defineProps<{
  show: boolean
  settings: AssistantSettings
  globalSettings?: Settings | null
  allowWebSearch: boolean
  allowWriteMemory: boolean
  allowDestructiveTools: boolean
}>()

const emit = defineEmits<{
  cancel: []
  save: [settings: AssistantSettings, permissions: {
    allowWebSearch: boolean
    allowWriteMemory: boolean
    allowDestructiveTools: boolean
  }]
}>()

const draft = ref({ ...props.settings })
const permissions = ref({
  allowWebSearch: props.allowWebSearch,
  allowWriteMemory: props.allowWriteMemory,
  allowDestructiveTools: props.allowDestructiveTools,
})
watch(() => props.show, (show) => {
  if (!show) return
  draft.value = { ...props.settings }
  permissions.value = {
    allowWebSearch: props.allowWebSearch,
    allowWriteMemory: props.allowWriteMemory,
    allowDestructiveTools: props.allowDestructiveTools,
  }
}, { immediate: true })

const titleId = 'assistant-settings-title'
const dialogAttrs = dialogAria(titleId)
const { dialogRef } = useDialogBehavior(
  () => props.show,
  () => emit('cancel'),
)
void dialogRef

const effectiveModel = computed(() => (draft.value.model || props.globalSettings?.llm.defaultModel || '').trim())
const modelConnection = computed(() => effectiveModel.value && props.globalSettings
  ? resolveModelConnection(props.globalSettings, effectiveModel.value, draft.value.presetId)
  : null)
const previewConnection = computed(() => {
  const connection = modelConnection.value
  const settings = props.globalSettings
  if (!connection?.configured || !settings) return null
  const credentials = connection.presetId
    ? settings.apiPresets.find(preset => preset.id === connection.presetId)
    : settings.llm
  if (!credentials?.baseUrl?.trim()) return null
  return {
    model: connection.model,
    baseUrl: credentials.baseUrl,
    protocol: credentials.protocol,
    providerId: credentials.providerId,
    providerParams: credentials.providerParams,
    authStyle: credentials.authStyle,
  }
})
const requestedEffort = computed(() => normalizeReasoningEffort(draft.value.reasoningEffort ?? props.globalSettings?.reasoningEffort))
const { preview, resolvedRequest, error } = useProtocolPreview(
  () => previewConnection.value ? { ...previewConnection.value, reasoningEffort: requestedEffort.value, fastMode: true } : null,
  { enabled: () => props.show, debounceMs: 100 },
)

function connectionKey(request: ResolvePreviewRequest | null) {
  return request && JSON.stringify([request.model, request.baseUrl, request.protocol, request.providerId,
    request.providerParams, request.authStyle])
}
const capability = computed(() => connectionKey(resolvedRequest.value) === connectionKey(previewConnection.value) ? preview.value : null)
const effortOptions = computed(() => REASONING_EFFORT_VALUES.filter(value => capability.value?.availableEfforts.includes(value))
  .map(value => ({ value, label: REASONING_EFFORT_SHORT_LABELS[value], ariaLabel: `思考深度 ${REASONING_EFFORT_SHORT_LABELS[value]}` })))
const effectiveEffort = computed(() => effortOptions.value.some(option => option.value === requestedEffort.value)
  ? requestedEffort.value : normalizeReasoningEffort(capability.value?.effort))
const thinkingEnabled = computed(() => !!capability.value && effectiveEffort.value !== 'none')
const supportsFast = computed(() => capability.value?.fastMode === true)
const capabilityStatus = computed(() => {
  if (!effectiveModel.value) return '请先在助手面板选择模型。'
  if (!previewConnection.value) return '请检查助手模型的连接设置。'
  return error.value ? '暂时无法读取模型能力。' : '正在读取模型能力…'
})
const fastHint = computed(() => {
  if (supportsFast.value) return '约 2× 计费。'
  if (!capability.value) return undefined
  return draft.value.fastMode ? '当前模型或连接不支持，可关闭原有的 Fast 设置。' : '当前模型或连接不支持。'
})

function selectEffort(value: string | number | null) {
  if (effortOptions.value.some(option => option.value === value)) draft.value.reasoningEffort = value as ReasoningEffort
}
</script>

<template>
  <Transition name="modal">
    <div v-if="show" class="modal">
      <div class="modal-backdrop backdrop-blur-[var(--glass-blur-soft)]" @click="emit('cancel')"></div>
      <div ref="dialogRef" v-bind="dialogAttrs" tabindex="-1" class="modal-content modal-surface chat-modal-width-520-92">
        <div class="modal-header">
          <h3 :id="titleId" class="modal-title">聊天助手设置</h3>
          <button type="button" class="modal-close" aria-label="关闭聊天助手设置弹窗" @click="emit('cancel')">
            <X class="w-5 h-5" />
          </button>
        </div>
        <div class="modal-body">
          <div class="assistant-model-settings settings-group">
            <div class="settings-group-title">模型</div>
            <div class="assistant-model-summary space-y-1 text-xs">
              <p class="[overflow-wrap:anywhere] text-[var(--color-text-secondary)]">
                <template v-if="modelConnection">
                  {{ draft.model ? '助手自定义模型' : '沿用全局模型' }} · {{ modelConnection.model }} · {{ modelConnection.connection }}
                  <span v-if="modelConnection.issue" class="text-warning"> · {{ modelConnection.issue }}</span>
                </template>
                <template v-else>未选择助手模型</template>
              </p>
              <p class="text-[var(--color-text-muted)]">主聊天助手和角色工作区共用</p>
            </div>
            <p v-if="!capability" class="settings-hint" role="status">{{ capabilityStatus }}</p>
            <SettingsField label="温度" :hint="thinkingEnabled ? '思考启用时，请求会忽略温度。已填值会保留。' : undefined">
              <input
                v-model.number="draft.temperature"
                type="number"
                min="0"
                max="2"
                step="0.1"
                aria-label="温度"
                placeholder="使用模型默认值"
                :disabled="thinkingEnabled"
                class="input w-full"
              />
            </SettingsField>
            <SettingsField v-if="effortOptions.length" label="思考深度">
              <template #actions>
                <button v-if="draft.reasoningEffort != null" class="btn btn-xs btn-link shrink-0" type="button"
                  @click="draft.reasoningEffort = null">恢复沿用全局</button>
                <span v-else class="settings-hint shrink-0">沿用全局</span>
              </template>
              <ReasoningEffortSegments
                class="assistant-effort-segments"
                :model-value="effectiveEffort"
                :options="effortOptions"
                @update:model-value="selectEffort"
              />
              <ModernSelect
                :model-value="effectiveEffort"
                :options="effortOptions"
                class="assistant-effort-select w-full"
                aria-label="思考深度"
                @update:model-value="selectEffort"
              />
            </SettingsField>
            <SettingsSwitch
              label="Fast 模式"
              :model-value="!!draft.fastMode"
              :hint="fastHint"
              :disabled="!supportsFast && !draft.fastMode"
              @update:model-value="(v) => { draft.fastMode = v ? true : null }"
            />
          </div>

          <div class="settings-group">
            <div class="settings-group-title">上下文与读取</div>
            <SettingsField
              label="上下文长度"
              more="填 0 或留空表示不限制。角色卡、用户信息和系统提示词不计入这个长度。"
            >
              <input
                v-model.number="draft.context_size"
                type="number"
                min="0"
                class="input w-full"
                placeholder="未启用（不限制）"
              />
            </SettingsField>
            <SettingsField
              label="助手读取消息条数上限"
              more="限制「读取会话」工具返回的消息条数，留空不额外限制。"
            >
              <input
                v-model.number="draft.tool_read_max_messages"
                type="number"
                min="1"
                class="input w-full"
                placeholder="未限制（仅受服务端硬上限）"
              />
            </SettingsField>
            <SettingsField
              label="助手读取消息 token 上限（估算）"
              more="按 token 估算裁剪读到的消息，保留最新的；留空不启用。"
            >
              <input
                v-model.number="draft.tool_read_max_tokens"
                type="number"
                min="1"
                class="input w-full"
                placeholder="未限制"
              />
            </SettingsField>
          </div>

          <div class="settings-group">
            <div class="settings-group-title">工具调用</div>
            <SettingsField label="最大工具轮次" more="单次请求里，助手最多连续调用工具的轮数。">
              <input
                v-model.number="draft.maxToolTurns"
                type="number"
                min="1"
                class="input w-full"
                placeholder="默认 8"
              />
            </SettingsField>
            <SettingsField label="单轮工具数上限" more="超出的工具调用会被跳过，并返回「超出限制」。">
              <input
                v-model.number="draft.maxToolsPerTurn"
                type="number"
                min="1"
                class="input w-full"
                placeholder="未限制"
              />
            </SettingsField>
          </div>

          <div class="settings-group">
            <div class="settings-group-title">工具权限</div>
            <SettingsSwitch
              label="允许网络搜索"
              :model-value="permissions.allowWebSearch"
              @update:model-value="permissions.allowWebSearch = $event"
            />
            <SettingsSwitch
              label="允许记忆写入"
              :model-value="permissions.allowWriteMemory"
              more="聊天助手可以追加或覆盖当前会话的长期记忆。"
              @update:model-value="permissions.allowWriteMemory = $event"
            />
            <SettingsSwitch
              label="允许破坏性工具"
              :model-value="permissions.allowDestructiveTools"
              more="开启后助手可执行删除文件、删除世界书、覆盖整卡与覆盖全部记忆等不可逆操作。"
              @update:model-value="permissions.allowDestructiveTools = $event"
            />
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="emit('cancel')">取消</button>
          <button class="btn btn-primary" @click="emit('save', draft, permissions)">保存</button>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.assistant-model-settings { container-type: inline-size; }
.assistant-effort-select { display: none; }

@container (width < 20rem) {
  .assistant-effort-segments { display: none; }
  .assistant-effort-select { display: block; }
}
</style>
