<script setup lang="ts">
/**
 * MemberSettingsModal - 群聊成员设置弹窗组件
 *
 * 组件职责：
 * - 编辑单个群成员的专属设置
 * - 支持设置模型、温度、top_p、发言概率等参数
 * - 支持设置是否包含性格和场景描述
 *
 * Props说明：
 * - show: 是否显示弹窗（v-model:show）
 * - memberId: 成员角色ID
 * - settings: 成员设置（来自types/models.ts的GroupMemberSettings类型，v-model:settings）
 * - character: 成员角色信息（来自types/models.ts的CharacterCard类型）
 * - modelOptions: 模型选项列表
 *
 * Emits说明：
 * - update:show: 更新显示状态（v-model:show）
 * - update:settings: 更新成员设置（v-model:settings）
 * - save: 保存设置
 *
 * 使用的Composables：
 * 无
 *
 * 使用的Stores：
 * 无
 *
 * 文件关系：
 *    - 被导入：被views/ChatPage.vue使用
 *    - 导入：导入types/models.ts的类型、components/ModernAvatar.vue、components/ModernSelect.vue
 *    - 依赖：依赖vue
 *    - 位置：组件层，提供成员设置编辑功能
 */
import { X } from 'lucide-vue-next'
import type { GroupMemberSettings, CharacterCard } from '../../types/models'
import { REASONING_EFFORT_OPTIONS } from '../../types/models'
import ModernAvatar from '../ModernAvatar.vue'
import ModernSelect from '../ModernSelect.vue'
import SettingsField from '../settings-drawer/SettingsField.vue'
import SettingsSwitch from '../settings-drawer/SettingsSwitch.vue'
import SettingsHint from '../settings-drawer/SettingsHint.vue'
import { useDialogBehavior } from '../../composables/useDialogBehavior'
import { dialogAria } from '../../utils/uiPrimitives'

interface ModelOption {
  label: string
  value: string
  presetId?: string | null
}

interface ModelOptionGroup {
  label: string
  options: ModelOption[]
}

const props = defineProps<{
  show: boolean
  memberId: string | null
  settings: GroupMemberSettings
  character: CharacterCard | null
  modelOptions: (ModelOption | ModelOptionGroup | string)[]
}>()

const emit = defineEmits<{
  'update:show': [value: boolean]
  'update:settings': [settings: GroupMemberSettings]
  'save': []
}>()

/**
 * 更新设置字段
 *
 * 更新成员设置的指定字段，触发update:settings事件。
 *
 * @template K - 字段键类型
 * @param {K} field - 字段名
 * @param {GroupMemberSettings[K]} value - 字段值
 */
function updateField<K extends keyof GroupMemberSettings>(field: K, value: GroupMemberSettings[K]) {
  emit('update:settings', { ...props.settings, [field]: value })
}

/**
 * 处理模型选择
 *
 * 更新成员设置的模型和预设ID。
 * 如果值为空字符串，则转换为null。
 *
 * @param {{ value: string; presetId?: string }} opt - 模型选项
 */
function handleModelSelect(opt: { value: string; presetId?: string }) {
  emit('update:settings', { 
    ...props.settings, 
    model: opt.value || null,
    presetId: opt.presetId ?? null 
  })
}

/** 留空恢复默认 100%；0 是有效值，表示这名成员通常不发言 */
function onProbabilityInput(event: Event) {
  const raw = (event.target as HTMLInputElement).value
  if (raw.trim() === '') {
    updateField('probability', 1)
    return
  }
  const value = parseFloat(raw)
  if (Number.isFinite(value)) updateField('probability', Math.max(0, Math.min(1, value)))
}

function clearBoundModel() {
  emit('update:settings', { ...props.settings, model: null, presetId: null })
}

/**
 * 关闭弹窗
 *
 * 触发update:show事件，传递false。
 */
function close() {
  emit('update:show', false)
}

const titleId = 'member-settings-title'
const dialogAttrs = dialogAria(titleId)
const { dialogRef } = useDialogBehavior(() => props.show && !!props.memberId, close)
void dialogRef

/**
 * 保存设置
 *
 * 触发save事件。
 */
function save() {
  emit('save')
}

const effortOptions = [
  { label: '沿用会话 / 全局', value: '' },
  ...REASONING_EFFORT_OPTIONS.map((o) => ({ label: o.label, value: o.value })),
]
function effortValue(): string {
  return props.settings.reasoningEffort ?? ''
}

const fastOptions = [
  { label: '沿用会话 / 全局', value: '' },
  { label: '开启', value: 'on' },
  { label: '关闭', value: 'off' },
]
function fastValue(): string {
  if (props.settings.fastMode === true) return 'on'
  if (props.settings.fastMode === false) return 'off'
  return ''
}
function setFast(v: string) {
  const next = String(v)
  updateField('fastMode', next === 'on' ? true : next === 'off' ? false : null)
}
</script>

<template>
  <Transition name="modal">
    <div v-if="show && memberId" class="modal">
      <div class="modal-backdrop backdrop-blur-[var(--glass-blur-soft)]" @click="close"></div>
      <div ref="dialogRef" v-bind="dialogAttrs" tabindex="-1" class="modal-content modal-surface chat-modal-width-500-90">
        <div class="modal-header">
          <h3 :id="titleId" class="modal-title">成员设置</h3>
          <button type="button" class="modal-close" aria-label="关闭成员设置弹窗" @click="close">
            <X class="w-5 h-5" />
          </button>
        </div>
        <div class="modal-body">
          <div v-if="character" class="settings-group">
            <div class="flex items-center gap-3">
              <ModernAvatar
                :src="character.avatar ? `/api/avatars/${character.avatar}` : null"
                :name="character.name"
                :size="48"
                aspect="0.75"
                rounded="rounded-lg"
              />
              <div class="min-w-0">
                <div class="settings-group-title truncate">{{ character.name }}</div>
                <div class="settings-hint">独立设置（覆盖全局）</div>
              </div>
            </div>
          </div>

          <div class="settings-group">
            <div class="settings-group-title">模型</div>
            <SettingsField label="绑定模型">
              <template #actions>
                <button
                  type="button"
                  class="btn btn-xs btn-secondary shrink-0"
                  :disabled="!settings.model && !settings.presetId"
                  @click="clearBoundModel"
                >
                  清除
                </button>
              </template>
              <ModernSelect
                :model-value="settings.model"
                :selected-preset-id="settings.presetId ?? null"
                :options="modelOptions"
                placement="bottom"
                placeholder="使用全局模型..."
                class="w-full"
                searchable
                allow-create
                @select="handleModelSelect"
              />
            </SettingsField>
            <SettingsField label="Temperature (覆写)">
              <input
                type="number"
                :value="settings.temperature ?? ''"
                class="input w-full"
                placeholder="使用全局设置"
                min="0"
                max="2"
                step="0.1"
                @input="updateField('temperature', ($event.target as HTMLInputElement).value ? parseFloat(($event.target as HTMLInputElement).value) : null)"
              />
            </SettingsField>
            <SettingsField label="Top P (覆写)">
              <input
                type="number"
                :value="settings.top_p ?? ''"
                class="input w-full"
                placeholder="使用全局设置"
                min="0"
                max="1"
                step="0.05"
                @input="updateField('top_p', ($event.target as HTMLInputElement).value ? parseFloat(($event.target as HTMLInputElement).value) : null)"
              />
            </SettingsField>
            <SettingsField
              label="思考深度"
              more="留空沿用会话或全局默认；none 会真正关闭思考。"
            >
              <ModernSelect
                :model-value="effortValue()"
                :options="effortOptions"
                class="w-full"
                placeholder="沿用会话 / 全局…"
                @update:model-value="(v) => updateField('reasoningEffort', String(v) ? String(v) as GroupMemberSettings['reasoningEffort'] : null)"
              />
            </SettingsField>
            <SettingsField label="Fast 模式" hint="约 2× 计费。" more="选「关闭」会覆盖会话里已打开的 Fast。">
              <ModernSelect
                :model-value="fastValue()"
                :options="fastOptions"
                class="w-full"
                placeholder="沿用会话 / 全局…"
                @update:model-value="(v) => setFast(String(v))"
              />
            </SettingsField>
          </div>

          <div class="settings-group">
            <div class="settings-group-title">发言</div>
            <SettingsField
              label="参与概率"
              more="100% 每轮必定发言，低于 100% 按概率参与，0 通常不发言。一轮里没人被选中时，会随机保留一名。"
            >
              <div class="flex items-center gap-3">
                <input
                  type="number"
                  :value="settings.probability"
                  class="input w-24"
                  min="0"
                  max="1"
                  step="0.1"
                  @input="onProbabilityInput"
                />
                <div class="flex-1">
                  <div class="h-2 bg-[var(--color-surface-muted)] rounded-full overflow-hidden">
                    <div
                      class="h-full bg-[var(--color-success)] transition-[width] duration-[var(--motion-duration-expand)] ease-out"
                      :style="{ width: `${(settings.probability ?? 1) * 100}%` }"
                    ></div>
                  </div>
                </div>
                <span class="text-sm text-muted w-12 text-right">{{ Math.round((settings.probability ?? 1) * 100) }}%</span>
              </div>
            </SettingsField>
          </div>

          <div class="settings-group">
            <SettingsHint title="system prompt 插入字段" more="关闭后，这名成员对应的字段不再注入 system prompt，可以避免多人共享世界观时重复设定。" />
            <SettingsSwitch
              label="插入 Personality"
              :model-value="settings.includePersonality !== false"
              @update:model-value="updateField('includePersonality', $event)"
            />
            <SettingsSwitch
              label="插入 Scenario"
              :model-value="settings.includeScenario !== false"
              @update:model-value="updateField('includeScenario', $event)"
            />
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="close">取消</button>
          <button class="btn btn-primary" @click="save">保存</button>
        </div>
      </div>
    </div>
  </Transition>
</template>
