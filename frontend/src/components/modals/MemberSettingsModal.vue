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
import type { GroupMemberSettings, CharacterCard } from '../../types/models'
import ModernAvatar from '../ModernAvatar.vue'
import ModernSelect from '../ModernSelect.vue'

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

/**
 * 关闭弹窗
 *
 * 触发update:show事件，传递false。
 */
function close() {
  emit('update:show', false)
}

/**
 * 保存设置
 *
 * 触发save事件。
 */
function save() {
  emit('save')
}
</script>

<template>
  <Transition name="modal">
    <div v-if="show && memberId" class="modal">
      <div class="modal-backdrop" @click="close"></div>
      <div class="modal-content chat-modal-width-500-90 glass-panel">
        <div class="modal-header">
          <h3 class="modal-title text-slate-50">成员设置</h3>
          <button class="modal-close" @click="close">×</button>
        </div>
        <div class="modal-body space-y-6">
          <!-- 角色信息 -->
          <div v-if="character" class="flex items-center gap-3 pb-4 border-b border-white/10">
            <ModernAvatar 
              :src="character.avatar ? `/api/avatars/${character.avatar}` : null" 
              :name="character.name" 
              :size="48" 
              aspect="0.75"
              rounded="rounded-lg"
            />
            <div>
              <div class="font-bold text-lg text-gray-200">{{ character.name }}</div>
              <div class="text-xs text-gray-500">独立设置（覆盖全局）</div>
            </div>
          </div>

          <!-- 模型绑定 -->
          <div class="form-group">
            <label class="label">绑定模型</label>
            <ModernSelect
              :model-value="settings.model"
              :options="modelOptions"
              placement="bottom"
              placeholder="使用全局模型..."
              class="w-full"
              searchable
              allow-create
              @select="handleModelSelect"
            />
            <div class="form-hint">为该成员绑定专属模型，留空则使用全局设置</div>
          </div>

          <!-- Temperature -->
          <div class="form-group">
            <label class="label">Temperature (覆写)</label>
            <input 
              type="number"
              :value="settings.temperature ?? ''"
              @input="updateField('temperature', ($event.target as HTMLInputElement).value ? parseFloat(($event.target as HTMLInputElement).value) : null)"
              class="input bg-black/20 border-white/10 focus:border-brand/50"
              placeholder="使用全局设置"
              min="0"
              max="2"
              step="0.1"
            />
          </div>

          <!-- Top P -->
          <div class="form-group">
            <label class="label">Top P (覆写)</label>
            <input 
              type="number"
              :value="settings.top_p ?? ''"
              @input="updateField('top_p', ($event.target as HTMLInputElement).value ? parseFloat(($event.target as HTMLInputElement).value) : null)"
              class="input bg-black/20 border-white/10 focus:border-brand/50"
              placeholder="使用全局设置"
              min="0"
              max="1"
              step="0.05"
            />
          </div>

          <!-- 参与概率 -->
          <div class="form-group">
            <label class="label">参与概率</label>
            <div class="flex items-center gap-3">
              <input 
                type="number"
                :value="settings.probability"
                @input="updateField('probability', parseFloat(($event.target as HTMLInputElement).value) || 1)"
                class="input w-24 bg-black/20 border-white/10 focus:border-brand/50"
                min="0"
                max="1"
                step="0.1"
              />
              <div class="flex-1">
                <div class="h-2 bg-white/10 rounded-full overflow-hidden">
                  <div 
                    class="h-full bg-gradient-to-r from-yellow-500 to-green-500 transition-all"
                    :style="{ width: `${(settings.probability ?? 1) * 100}%` }"
                  ></div>
                </div>
              </div>
              <span class="text-sm text-gray-400 w-12 text-right">{{ Math.round((settings.probability ?? 1) * 100) }}%</span>
            </div>
            <div class="form-hint">设置为 100% 表示每轮必定发言，低于 100% 则按概率随机参与</div>
          </div>

          <!-- system prompt 插入字段 -->
          <div class="form-group">
            <label class="label">system prompt 插入字段</label>
            <div class="flex flex-wrap gap-4">
              <label class="flex items-center gap-2 text-sm text-gray-300 cursor-pointer">
                <input 
                  type="checkbox" 
                  class="accent-brand" 
                  :checked="settings.includePersonality !== false"
                  @change="updateField('includePersonality', ($event.target as HTMLInputElement).checked)"
                />
                插入 Personality
              </label>
              <label class="flex items-center gap-2 text-sm text-gray-300 cursor-pointer">
                <input 
                  type="checkbox" 
                  class="accent-brand" 
                  :checked="settings.includeScenario !== false"
                  @change="updateField('includeScenario', ($event.target as HTMLInputElement).checked)"
                />
                插入 Scenario
              </label>
            </div>
            <div class="form-hint">
              关闭后，该成员对应字段将不会被注入到本轮/后续的 system prompt（用于避免多人共享世界观时的重复设定）。
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary bg-white/5 hover:bg-white/10 text-gray-300 border border-white/5" @click="close">取消</button>
          <button class="btn btn-primary bg-brand hover:bg-brand-hover text-white shadow-lg shadow-brand/20" @click="save">保存</button>
        </div>
      </div>
    </div>
  </Transition>
</template>
