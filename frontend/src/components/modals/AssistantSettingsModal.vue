<script setup lang="ts">
import { X } from 'lucide-vue-next'
import ThemedCheckbox from '../ThemedCheckbox.vue'
import ModernSelect from '../ModernSelect.vue'
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
  <div v-if="show" class="modal">
    <div class="modal-backdrop" @click="emit('cancel')"></div>
    <div ref="dialogRef" v-bind="dialogAttrs" tabindex="-1" class="modal-content modal-surface chat-modal-width-520-92">
      <div class="modal-header">
        <h3 :id="titleId" class="modal-title">聊天助手设置</h3>
        <button type="button" class="modal-close" aria-label="关闭聊天助手设置弹窗" @click="emit('cancel')">
          <X class="w-5 h-5" />
        </button>
      </div>
      <div class="modal-body">
        <div class="space-y-6">
          <div class="form-group">
            <label class="label">温度</label>
            <input
              v-model.number="settings.temperature"
              type="number"
              min="0"
              max="2"
              step="0.1"
              class="input w-full"
            />
          </div>
          <div class="form-group">
            <label class="label">思考深度</label>
            <ModernSelect
              :model-value="effortValue()"
              :options="effortOptions"
              class="w-full"
              placeholder="沿用全局…"
              @update:model-value="(v) => { settings.reasoningEffort = String(v) ? String(v) : null }"
            />
            <p class="text-xs text-[var(--color-text-muted)] mt-1">none 会真正关闭思考。留空则沿用全局设置里的默认深度。</p>
          </div>
          <div class="form-group">
            <button
              type="button"
              class="flex w-full items-center justify-between gap-3 text-left"
              role="switch"
              :aria-checked="!!settings.fastMode"
              @click="settings.fastMode = settings.fastMode ? null : true"
            >
              <span>
                <span class="block text-sm text-[var(--color-text)]">Fast 模式</span>
                <span class="block text-xs text-[var(--color-text-muted)] mt-1">约 2× 计费。不支持的模型会在发送时明确报错。</span>
              </span>
              <span class="relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors" :class="settings.fastMode ? 'bg-brand' : 'bg-[var(--color-track)]'">
                <span class="absolute h-4 w-4 rounded-full bg-[var(--color-on-brand)] shadow transition-transform" :class="settings.fastMode ? 'translate-x-4' : 'translate-x-0.5'" />
              </span>
            </button>
          </div>
          <div class="form-group">
            <label class="label">上下文长度</label>
            <input
              v-model.number="settings.context_size"
              type="number"
              min="0"
              class="input w-full"
              placeholder="未启用（不限制）"
            />
            <p class="text-xs text-[var(--color-text-muted)] mt-1">填 0 或留空表示未启用。实际上下文总限制长度为该「上下文长度」限制加上角色卡、用户信息、自定义系统提示词。</p>
          </div>
          <div class="form-group">
            <label class="label">助手读取消息条数上限</label>
            <input
              v-model.number="settings.tool_read_max_messages"
              type="number"
              min="1"
              class="input w-full"
              placeholder="未限制（仅受服务端硬上限）"
            />
            <p class="text-xs text-[var(--color-text-muted)] mt-1">限制「读取会话」工具返回的最大消息条数；留空表示不额外限制。</p>
          </div>
          <div class="form-group">
            <label class="label">助手读取消息 token 上限（估算）</label>
            <input
              v-model.number="settings.tool_read_max_tokens"
              type="number"
              min="1"
              class="input w-full"
              placeholder="未限制"
            />
            <p class="text-xs text-[var(--color-text-muted)] mt-1">对返回的消息列表做 token 估算裁剪（保留最新）；留空表示不启用。</p>
          </div>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div class="form-group">
              <label class="label">最大工具轮次</label>
              <input
                v-model.number="settings.maxToolTurns"
                type="number"
                min="1"
                class="input w-full"
                placeholder="默认 8"
              />
              <p class="text-xs text-[var(--color-text-muted)] mt-1">限制单次助手请求可进入多少轮 tool_calls。</p>
            </div>
            <div class="form-group">
              <label class="label">单轮工具数上限</label>
              <input
                v-model.number="settings.maxToolsPerTurn"
                type="number"
                min="1"
                class="input w-full"
                placeholder="未限制"
              />
              <p class="text-xs text-[var(--color-text-muted)] mt-1">超出部分会写入「超出限制」占位结果并跳过执行。</p>
            </div>
          </div>
          <div class="form-group border-t border-[var(--color-border-subtle)] pt-6">
            <p class="label mb-3">工具权限</p>
            <p class="text-xs text-[var(--color-text-muted)] mb-4">
              以下开关与侧栏消息列表底部的权限按钮同步，变更后立即写入本机偏好。
            </p>
            <label class="flex items-start gap-3 cursor-pointer mb-4">
              <ThemedCheckbox
                class="mt-0.5"
                :checked="allowWebSearch"
                @update:checked="emit('update:allowWebSearch', $event)"
              />
              <span>
                <span class="text-sm text-[var(--color-text)]">允许网络搜索</span>
                <span class="block text-xs text-[var(--color-text-muted)] mt-1">
                  开启后聊天助手与工具区助手可调用全局设置里的 Tavily / 博查 / Brave 搜索；MVU Agent 不会挂载此工具。
                </span>
              </span>
            </label>
            <label class="flex items-start gap-3 cursor-pointer mb-4">
              <ThemedCheckbox
                class="mt-0.5"
                :checked="allowWriteMemory"
                @update:checked="emit('update:allowWriteMemory', $event)"
              />
              <span>
                <span class="text-sm text-[var(--color-text)]">允许记忆写入</span>
                <span class="block text-xs text-[var(--color-text-muted)] mt-1">
                  开启后助手可在当前聊天会话中追加或覆盖长期记忆；仅作用于「聊天助手」，工作区助手不可用。
                </span>
              </span>
            </label>
            <label class="flex items-start gap-3 cursor-pointer">
              <ThemedCheckbox
                class="mt-0.5"
                :checked="allowDestructiveTools"
                @update:checked="emit('update:allowDestructiveTools', $event)"
              />
              <span>
                <span class="text-sm text-[var(--color-text)]">允许破坏性工具</span>
                <span class="block text-xs text-[var(--color-text-muted)] mt-1">
                  开启后助手可执行删除文件、删除世界书、覆盖整卡与覆盖全部记忆等不可逆操作。
                </span>
              </span>
            </label>
          </div>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" @click="emit('cancel')">取消</button>
        <button class="btn btn-primary" @click="emit('save')">保存</button>
      </div>
    </div>
  </div>
</template>
