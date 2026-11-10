<script setup lang="ts">
import { X } from 'lucide-vue-next'
import ModernSelect from '../ModernSelect.vue'
import SettingsField from '../settings-drawer/SettingsField.vue'
import SettingsSwitch from '../settings-drawer/SettingsSwitch.vue'
import SettingsHint from '../settings-drawer/SettingsHint.vue'
import type { AssistantSettings } from '../../composables/useAssistant'
import { useDialogBehavior } from '../../composables/useDialogBehavior'
import { dialogAria } from '../../utils/uiPrimitives'
import { REASONING_EFFORT_OPTIONS } from '../../types/models'

const props = defineProps<{
  show: boolean
  settings: AssistantSettings
  allowWebSearch: boolean
  allowWriteMemory: boolean
  allowDestructiveTools: boolean
}>()

const emit = defineEmits<{
  cancel: []
  save: []
  'update:allowWebSearch': [value: boolean]
  'update:allowWriteMemory': [value: boolean]
  'update:allowDestructiveTools': [value: boolean]
}>()

const titleId = 'assistant-settings-title'
const dialogAttrs = dialogAria(titleId)
const { dialogRef } = useDialogBehavior(
  () => props.show,
  () => emit('cancel'),
)
void dialogRef

const effortOptions = [
  { label: '沿用全局', value: '' },
  ...REASONING_EFFORT_OPTIONS.map((o) => ({ label: o.label, value: o.value })),
]
function effortValue(): string {
  return props.settings.reasoningEffort ?? ''
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
          <div class="settings-group">
            <div class="settings-group-title">模型</div>
            <SettingsField label="温度">
              <input
                v-model.number="settings.temperature"
                type="number"
                min="0"
                max="2"
                step="0.1"
                class="input w-full"
              />
            </SettingsField>
            <SettingsField
              label="思考深度"
              more="留空沿用全局默认；none 会真正关闭思考。"
            >
              <ModernSelect
                :model-value="effortValue()"
                :options="effortOptions"
                class="w-full"
                placeholder="沿用全局…"
                @update:model-value="(v) => { settings.reasoningEffort = String(v) ? String(v) : null }"
              />
            </SettingsField>
            <SettingsSwitch
              label="Fast 模式"
              :model-value="!!settings.fastMode"
              hint="约 2× 计费。"
              @update:model-value="(v) => { settings.fastMode = v ? true : null }"
            />
          </div>

          <div class="settings-group">
            <div class="settings-group-title">上下文与读取</div>
            <SettingsField
              label="上下文长度"
              more="填 0 或留空表示不限制。角色卡、用户信息和系统提示词不计入这个长度。"
            >
              <input
                v-model.number="settings.context_size"
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
                v-model.number="settings.tool_read_max_messages"
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
                v-model.number="settings.tool_read_max_tokens"
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
                v-model.number="settings.maxToolTurns"
                type="number"
                min="1"
                class="input w-full"
                placeholder="默认 8"
              />
            </SettingsField>
            <SettingsField label="单轮工具数上限" more="超出的工具调用会被跳过，并返回「超出限制」。">
              <input
                v-model.number="settings.maxToolsPerTurn"
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
              :model-value="allowWebSearch"
              more="聊天助手和工具区助手可以用全局设置里的搜索服务；MVU Agent 不会用。"
              @update:model-value="emit('update:allowWebSearch', $event)"
            />
            <SettingsSwitch
              label="允许记忆写入"
              :model-value="allowWriteMemory"
              more="助手可以追加或覆盖当前会话的长期记忆。只对聊天助手生效，工作区助手不可用。"
              @update:model-value="emit('update:allowWriteMemory', $event)"
            />
            <SettingsSwitch
              label="允许破坏性工具"
              :model-value="allowDestructiveTools"
              hint="操作不可逆。"
              more="开启后助手可执行删除文件、删除世界书、覆盖整卡与覆盖全部记忆等不可逆操作。"
              @update:model-value="emit('update:allowDestructiveTools', $event)"
            />
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="emit('cancel')">取消</button>
          <button class="btn btn-primary" @click="emit('save')">保存</button>
        </div>
      </div>
    </div>
  </Transition>
</template>
