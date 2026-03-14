<script setup lang="ts">
/**
 * ChatInput - 聊天输入组件
 *
 * 组件职责：
 * - 提供消息输入框和发送功能
 * - 显示群聊状态（当前发言者、暂停状态等）
 * - 提供插话面板，允许在群聊中触发角色插话
 * - 提供模型选择功能
 * - 根据状态显示不同的按钮标签和样式
 *
 * Props说明：
 * - modelValue: 输入框内容（v-model）
 * - isGenerating: 是否正在生成
 * - streamError: 流式传输错误信息
 * - isGroup: 是否为群聊
 * - groupMembers: 群聊成员列表
 * - currentSpeakerIndex: 当前发言者索引
 * - isPaused: 是否暂停
 * - showContinueButton: 是否显示继续按钮
 * - pendingMembersCount: 待发言成员数量
 * - canInterject: 是否可以插话
 * - showInterjectPanel: 是否显示插话面板
 * - isInterjecting: 是否正在插话
 * - effectivePureAiMode: 是否为纯AI模式
 * - isStreamingActive: 是否正在流式传输
 * - userAvatarUrl: 用户头像URL
 * - userName: 用户名称
 * - currentModel: 当前选中的模型
 * - modelOptions: 模型选项列表
 * - getMemberSettings: 获取成员设置的函数（来自composables/useGroupChat.ts）
 *
 * Emits说明：
 * - update:modelValue: 更新输入框内容（v-model）
 * - send: 发送消息
 * - primary-action: 主要操作（发送/停止/继续等）
 * - pause-group: 暂停群聊
 * - continue-group: 继续群聊
 * - trigger-interject: 触发插话，传递角色ID
 * - hide-interject: 隐藏插话面板
 * - select-model: 选择模型
 * - toggle-assistant: 切换助手面板
 *
 * 使用的Composables：
 * 无（通过props接收函数）
 *
 * 使用的Stores：
 * 无
 *
 * 文件关系：
 *    - 被导入：被views/ChatPage.vue使用
 *    - 导入：导入vue的computed、types/models.ts的类型、components/ModernAvatar.vue、components/ModernSelect.vue
 *    - 依赖：依赖vue
 *    - 位置：组件层，提供聊天输入功能
 */
import { computed, ref } from 'vue'
import type { CharacterCard, GroupMemberSettings } from '../../types/models'
import ModernAvatar from '../ModernAvatar.vue'
import ModernSelect from '../ModernSelect.vue'
import { ImagePlus, MessageSquare, X } from 'lucide-vue-next'

interface ModelOption {
  label: string
  value: string
  presetId?: string | null
}

interface ModelOptionGroup {
  label: string
  options: ModelOption[]
}

interface DraftImagePreview {
  id: string
  name: string
  previewUrl: string
}

const props = defineProps<{
  // 输入状态
  modelValue: string
  isGenerating: boolean
  streamError: string | null
  draftImages: DraftImagePreview[]
  
  // 群聊相关
  isGroup: boolean
  groupMembers: CharacterCard[]
  currentSpeakerIndex: number
  isPaused: boolean
  showContinueButton: boolean
  pendingMembersCount: number
  canInterject: boolean
  showInterjectPanel: boolean
  isInterjecting: boolean
  effectivePureAiMode: boolean
  isStreamingActive: boolean
  
  // 用户信息
  userAvatarUrl: string | null
  userName: string
  
  // 模型选择
  currentModel: string
  currentPresetId?: string | null
  modelOptions: (ModelOption | ModelOptionGroup | string)[]
  
  // 辅助函数
  getMemberSettings: (memberId: string) => GroupMemberSettings
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  'send': []
  'primary-action': []
  'pause-group': []
  'continue-group': []
  'trigger-interject': [characterId: string]
  'hide-interject': []
  'select-model': [option: any]
  'toggle-assistant': []
  'select-images': [files: File[]]
  'remove-image': [imageId: string]
}>()

const imageInputRef = ref<HTMLInputElement | null>(null)

/**
 * 计算是否有草稿消息
 *
 * 检查输入框是否有非空内容。
 */
const hasDraftMessage = computed(() => !!props.modelValue.trim() || props.draftImages.length > 0)

/**
 * 计算主要操作按钮标签
 *
 * 根据当前状态（流式传输、继续按钮、群聊等）返回相应的按钮标签。
 */
const primaryActionLabel = computed(() => {
  if (props.isStreamingActive) return '停止'
  if (props.showContinueButton && props.isGroup) {
    return hasDraftMessage.value ? '插话' : '继续轮次'
  }
  if (props.isGroup && !hasDraftMessage.value) {
    return '开始下一轮'
  }
  return props.isGenerating && !props.isPaused && !props.showContinueButton ? '生成中...' : '发送'
})

/**
 * 计算主要操作按钮是否禁用
 *
 * 根据当前状态判断按钮是否应该禁用。
 */
const primaryActionDisabled = computed(() => {
  if (props.isStreamingActive) return false
  if (props.showContinueButton && props.isGroup) return false
  if (props.isGroup && !hasDraftMessage.value) return props.isGenerating
  return !hasDraftMessage.value || (props.isGenerating && !props.isPaused && !props.showContinueButton)
})

/**
 * 计算主要操作按钮样式类
 *
 * 根据当前状态返回相应的CSS类名。
 */
const primaryActionClass = computed(() => {
  if (props.isStreamingActive) return 'chat-action-button--stop'
  if (props.showContinueButton && props.isGroup) {
    return hasDraftMessage.value ? 'chat-action-button--primary' : 'chat-action-button--continue'
  }
  if (props.isGroup && !hasDraftMessage.value) {
    return 'chat-action-button--next'
  }
  return 'chat-action-button--primary'
})

/**
 * 计算输入框占位符
 *
 * 根据当前状态返回相应的占位符文本。
 */
const inputPlaceholder = computed(() => {
  if (props.isGenerating && props.isGroup && !props.isPaused) {
    return '等待角色发言完成...'
  }
  if (props.showContinueButton) {
    return '输入消息插话，或点击继续轮次...'
  }
  return '发送消息...'
})

/**
 * 计算输入框是否禁用
 *
 * 在生成中且未暂停且未显示继续按钮时禁用输入框。
 */
const inputDisabled = computed(() => {
  return props.isGenerating && !props.isPaused && !props.showContinueButton
})

/**
 * 处理键盘事件
 *
 * 当按下Ctrl+Enter时触发发送事件。
 *
 * @param {KeyboardEvent} e - 键盘事件
 */
function handleKeydown(e: KeyboardEvent) {
  if (e.ctrlKey && e.key === 'Enter') {
    emit('send')
  }
}

function openImagePicker() {
  imageInputRef.value?.click()
}

function handleImageInputChange(e: Event) {
  const input = e.target as HTMLInputElement
  const files = Array.from(input.files || [])
  if (files.length) {
    emit('select-images', files)
  }
  input.value = ''
}
</script>

<template>
  <div class="shrink-0 p-4 pb-6 w-full max-w-4xl mx-auto z-20 relative overflow-visible" style="color: rgba(229, 231, 235, 1); background-color: unset; background: unset; opacity: 1;">
    <!-- 
      Refactored Container:
      - Uses bg-slate-900/70 and backdrop-blur-xl for strong glass effect
      - Uses border-white/10 for subtle border
      - Removed hardcoded hex colors
    -->
    <div class="relative bg-surface-overlay backdrop-blur-xl border border-[var(--color-border)] rounded-2xl shadow-xl p-3 flex flex-col gap-2 transition-all focus-within:border-brand/40 focus-within:ring-1 focus-within:ring-brand/20 focus-within:bg-surface-overlay" style="opacity: 1;">
      <textarea
        :value="modelValue"
        @input="emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)"
        :placeholder="inputPlaceholder"
        :disabled="inputDisabled"
        class="input textarea !bg-transparent !border-0 text-base resize-none min-h-[80px] text-primary placeholder-gray-500"
        :class="inputDisabled ? 'opacity-50' : ''"
        @keydown="handleKeydown"
      ></textarea>

      <div v-if="draftImages.length" class="flex flex-wrap gap-2 px-1">
        <div
          v-for="img in draftImages"
          :key="img.id"
          class="relative w-20 h-20 rounded-lg overflow-hidden border border-[var(--color-border)] bg-surface-muted"
        >
          <img :src="img.previewUrl" :alt="img.name" class="w-full h-full object-cover" />
          <button
            class="absolute top-1 right-1 w-5 h-5 rounded-full bg-black/60 text-white flex items-center justify-center"
            @click="emit('remove-image', img.id)"
          >
            <X class="w-3 h-3" />
          </button>
        </div>
      </div>
      
      <div class="flex items-center justify-between pt-2 border-t border-[var(--color-border-subtle)]">
        <div class="flex-1 min-w-0">
          <!-- 群聊发言状态指示器 -->
          <div v-if="isGroup && isGenerating && currentSpeakerIndex >= 0" class="flex items-center gap-2 text-xs text-[var(--color-purple)]">
            <span class="animate-pulse">●</span>
            <span>{{ groupMembers[currentSpeakerIndex]?.name || '角色' }} 正在发言...</span>
            <span class="text-[var(--color-text-muted)]">({{ currentSpeakerIndex + 1 }}/{{ groupMembers.length }})</span>
            <button 
              class="ml-2 px-2 py-0.5 text-xs bg-[var(--color-warning-bg)] hover:opacity-90 text-[var(--color-warning)] rounded transition-colors border border-[var(--color-warning)]/20"
              @click="emit('pause-group')"
            >
              暂停
            </button>
          </div>
          
          <!-- 继续轮次按钮 -->
          <div v-else-if="showContinueButton && pendingMembersCount > 0" class="flex items-center gap-2 text-xs text-green-400">
            <span>轮次已暂停，还有 {{ pendingMembersCount }} 位角色待发言</span>
            <button 
              class="px-3 py-1 text-xs bg-green-500/20 hover:bg-green-500/30 text-green-400 rounded transition-colors font-medium border border-green-500/20"
              @click="emit('continue-group')"
            >
              继续轮次
            </button>
          </div>
          
          <!-- 插话面板 -->
          <div v-else-if="canInterject && isGroup && !isInterjecting" class="flex items-center gap-2 text-xs">
            <span class="text-[var(--color-purple)] flex items-center gap-1"><MessageSquare class="w-3 h-3" /> 点击角色插话：</span>
            <div class="flex items-center gap-1">
              <div 
                v-for="member in groupMembers"
                :key="member.id"
                class="cursor-pointer hover:scale-110 transition-transform"
                :title="`让 ${member.name} 插话`"
                @click="emit('trigger-interject', member.id)"
              >
                <ModernAvatar 
                  :src="member.avatar ? `/api/avatars/${member.avatar}` : null" 
                  :name="member.name" 
                  :size="24" 
                  aspect="1"
                  rounded="rounded-lg"
                  class="ring-2 ring-purple-500/50 hover:ring-purple-500"
                />
              </div>
            </div>
            <button 
              class="ml-2 px-2 py-0.5 text-xs bg-surface-muted hover:bg-surface-hover text-[var(--color-text-muted)] rounded transition-colors border border-[var(--color-border-subtle)]"
              @click="emit('hide-interject')"
            >
              关闭
            </button>
          </div>
          
          <!-- 插话中状态 -->
          <div v-else-if="isInterjecting" class="flex items-center gap-2 text-xs text-[var(--color-purple)]">
            <span class="animate-pulse">●</span>
            <span>正在插话...</span>
          </div>
          
        </div>
        
        <div class="flex items-center gap-3">
          <button
            class="chat-action-button chat-action-button--secondary shadow-lg transition-all active:scale-95"
            :disabled="isGenerating && !showContinueButton"
            @click="openImagePicker"
            title="选择图片"
          >
            <ImagePlus class="w-4 h-4" />
          </button>
          <input
            ref="imageInputRef"
            type="file"
            accept="image/*"
            multiple
            class="hidden"
            @change="handleImageInputChange"
          />
          <ModernSelect
            :model-value="currentModel"
            :selected-preset-id="currentPresetId ?? null"
            :options="modelOptions"
            placement="top"
            placeholder="选择模型 (自动关联预设)..."
            class="!w-[200px] !text-xs"
            dropdown-width="410"
            searchable
            allow-create
            @select="emit('select-model', $event)"
          />
          <button 
            class="chat-action-button shadow-lg transition-all active:scale-95"
            :class="[primaryActionClass, primaryActionDisabled ? 'opacity-50 cursor-not-allowed' : 'hover:shadow-brand hover:-translate-y-0.5']"
            :disabled="primaryActionDisabled"
            @click="emit('primary-action')"
          >
            {{ primaryActionLabel }}
          </button>
        </div>
      </div>
    </div>
    
    <div class="text-center mt-2 text-xs text-[var(--color-text-muted)]">
      Markdown 支持 · Ctrl + Enter 发送
    </div>
    
    <!-- 助手按钮 -->
    <button
      class="assistant-button w-12 h-12 rounded-xl bg-assistant text-on-brand font-bold shadow-lg shadow-assistant/30 hover:bg-assistant/80 transition-all border border-[var(--color-border)] hover:scale-105 active:scale-95 flex items-center justify-center backdrop-blur-sm z-50"
      title="聊天助手"
      @click="emit('toggle-assistant')"
    >
      助手
    </button>
  </div>
</template>

<style scoped>
@reference "tailwindcss";

/* 组件特有样式，保持 scoped */
.textarea {
  scrollbar-width: none;
}
.textarea::-webkit-scrollbar {
  display: none;
}

.assistant-button {
  position: absolute;
  right: -4rem; /* -right-16 */
  bottom: 2.5rem; /* bottom-10 */
  margin-top: 49px;
  margin-bottom: 49px;
  background-color: var(--color-border-subtle);
}

@media (max-width: 2220px) {
  .assistant-button {
    position: fixed;
    top: 1rem;
    right: 1rem;
  }
}
</style>
