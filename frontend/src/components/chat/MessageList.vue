<script setup lang="ts">
/**
 * MessageList - 消息列表组件
 *
 * 组件职责：
 * - 显示聊天消息列表，包括用户消息、助手消息和系统消息
 * - 支持消息版本切换（查看不同版本）
 * - 支持消息编辑、删除、重写操作
 * - 支持Markdown渲染
 * - 自动滚动到底部
 * - 为流式输出设置DOM引用
 *
 * Props说明：
 * - messages: 消息列表（来自types/models.ts的ChatMessage[]类型）
 * - isGroup: 是否为群聊
 * - selectedCharacter: 当前选中的角色（来自types/models.ts的CharacterCard类型）
 * - characters: 角色列表（来自types/models.ts的CharacterCard[]类型）
 * - selectedPersona: 当前选中的用户身份（来自types/models.ts的UserPersona类型）
 * - userName: 用户名称
 * - userAvatarUrl: 用户头像URL
 * - characterAvatarUrl: 角色头像URL
 * - isGenerating: 是否正在生成
 * - getDisplayContent: 获取消息显示内容的函数（来自composables/useMessageVersions.ts）
 * - hasMultipleVersions: 检查是否有多个版本的函数（来自composables/useMessageVersions.ts）
 * - getCurrentVersionIndex: 获取当前版本索引的函数（来自composables/useMessageVersions.ts）
 * - getVersionCount: 获取版本总数的函数（来自composables/useMessageVersions.ts）
 *
 * Emits说明：
 * - edit-message: 编辑消息
 * - delete-message: 删除消息
 * - rewrite-message: 重写消息
 * - switch-previous-version: 切换到上一个版本
 * - switch-next-version: 切换到下一个版本
 * - set-content-ref: 设置消息内容的DOM引用（用于流式输出，传递给composables/useStreamOutput.ts）
 *
 * 使用的Composables：
 * 无（通过props接收函数）
 *
 * 使用的Stores：
 * 无
 *
 * 文件关系：
 *    - 被导入：被views/ChatPage.vue使用
 *    - 导入：导入vue的ref和nextTick、types/models.ts的类型、components/ModernAvatar.vue、markdown-it库
 *    - 依赖：依赖vue、markdown-it
 *    - 位置：组件层，提供消息列表显示功能
 */
import { ref, nextTick, computed } from 'vue'
import type { ChatMessage, CharacterCard, UserPersona } from '../../types/models'
import { useSettingsStore } from '../../stores'
import ModernAvatar from '../ModernAvatar.vue'
import ConfirmPopover from '../ConfirmPopover.vue'
import MarkdownIt from 'markdown-it'
import { Settings, ChevronLeft, ChevronRight } from 'lucide-vue-next'

const settingsStore = useSettingsStore()
/** 仅作用于消息气泡内文字的字号（来自全局设置） */
const messageContentFontSizeStyle = computed(() => {
  const px = settingsStore.settings?.messageFontSize
  return px != null ? { fontSize: `${px}px` } : {}
})

const props = defineProps<{
  messages: ChatMessage[]
  isGroup: boolean
  // 角色相关
  selectedCharacter: CharacterCard | null
  characters: CharacterCard[]
  // 用户相关
  selectedPersona: UserPersona | null
  userName: string
  userAvatarUrl: string | null
  characterAvatarUrl: string | null
  // 状态
  isGenerating: boolean
  // 版本相关
  getDisplayContent: (m: ChatMessage) => string
  hasMultipleVersions: (m: ChatMessage) => boolean
  getCurrentVersionIndex: (m: ChatMessage) => number
  getVersionCount: (m: ChatMessage) => number
}>()

const emit = defineEmits<{
  'edit-message': [m: ChatMessage]
  'delete-message': [m: ChatMessage]
  'rewrite-message': [m: ChatMessage]
  'switch-previous-version': [m: ChatMessage]
  'switch-next-version': [m: ChatMessage]
  'set-content-ref': [messageId: string, el: HTMLElement | null]
}>()

// 滚动容器引用
const scrollRef = ref<HTMLElement | null>(null)

// 删除确认状态
const deleteConfirm = ref<{
  message: ChatMessage
  target: HTMLElement
} | null>(null)

// Markdown 渲染器
const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
})

/**
 * 规范化Markdown输入
 *
 * 将Markdown中的引用语法（[name]:）中的冒号替换为中文冒号，避免被解析为链接定义。
 *
 * @param {string} text - Markdown文本
 * @returns {string} 规范化后的文本
 */
function normalizeMarkdownInput(text: string) {
  return (text ?? '').replace(/(^|\n)\[([^\]\n]+)\]:(\s*)/g, (_m, p1, name, sp) => `${p1}[${name}]：${sp}`)
}

/**
 * 渲染Markdown
 *
 * 使用MarkdownIt渲染Markdown文本为HTML。
 *
 * @param {string} text - Markdown文本
 * @returns {string} 渲染后的HTML
 */
function renderMarkdown(text: string) {
  return md.render(normalizeMarkdownInput(text))
}

/**
 * 获取角色信息
 *
 * 根据角色ID从角色列表中查找角色。
 *
 * @param {string} id - 角色ID
 * @returns {CharacterCard | null} 角色信息，如果未找到则返回null
 */
function getCharacterById(id: string): CharacterCard | null {
  return props.characters.find(c => c.id === id) ?? null
}

/**
 * 获取消息标签
 *
 * 根据消息角色和内容返回要显示的名称标签。
 * 用户消息显示发送者名称，助手消息显示角色名称，系统消息显示"系统"。
 *
 * @param {ChatMessage} m - 消息对象（来自types/models.ts）
 * @returns {string} 消息标签
 */
function getMessageLabel(m: ChatMessage): string {
  if (m.role === 'user') return (m.senderName || props.userName)
  if (m.role === 'assistant') {
    if (m.characterId) {
      const char = getCharacterById(m.characterId)
      return char?.name || 'AI'
    }
    return props.selectedCharacter?.name || 'AI'
  }
  return '系统'
}

/**
 * 获取消息头像
 *
 * 根据消息角色和内容返回头像URL。
 * 用户消息优先使用发送者头像，助手消息优先使用角色头像。
 *
 * @param {ChatMessage} m - 消息对象（来自types/models.ts）
 * @returns {string | null} 头像URL，如果未找到则返回null
 */
function getMessageAvatar(m: ChatMessage): string | null {
  if (m.role === 'user') {
    if (m.senderAvatar) return `/api/avatars/${m.senderAvatar}`
    return props.userAvatarUrl
  }
  if (m.role === 'assistant') {
    if (m.characterId) {
      const char = getCharacterById(m.characterId)
      return char?.avatar ? `/api/avatars/${char.avatar}` : null
    }
    return props.characterAvatarUrl
  }
  return null
}

/**
 * 确认删除消息
 *
 * 弹出确认对话框，确认后触发删除消息事件。
 *
 * @param {ChatMessage} m - 要删除的消息（来自types/models.ts）
 * @param {Event} event - 点击事件
 */
function confirmDelete(m: ChatMessage, event: Event) {
  deleteConfirm.value = {
    message: m,
    target: event.currentTarget as HTMLElement
  }
}

function handleConfirmDelete() {
  if (deleteConfirm.value) {
    emit('delete-message', deleteConfirm.value.message)
    deleteConfirm.value = null
  }
}

function cancelDelete() {
  deleteConfirm.value = null
}

/**
 * 滚动到底部
 *
 * 滚动消息列表容器到底部，显示最新消息。
 * 使用nextTick确保DOM更新后再滚动。
 */
function scrollToBottom() {
  nextTick(() => {
    if (scrollRef.value) {
      scrollRef.value.scrollTop = scrollRef.value.scrollHeight
    }
  })
}

// 暴露滚动方法
defineExpose({ scrollToBottom, scrollRef })
</script>

<template>
  <div 
    ref="scrollRef" 
    class="flex-1 overflow-y-auto p-4 pb-4 scroll-smooth custom-scrollbar" 
    :class="isGroup ? 'pt-32' : 'pt-24'"
    style="contain: content; transform: translateZ(0);"
  >
    <div class="max-w-4xl mx-auto space-y-8" style="padding-top: 98px;">
      <div 
        v-for="m in messages" 
        :key="m.id" 
        class="flex gap-4 group" 
        :class="m.role === 'user' ? 'flex-row-reverse' : 'flex-row'"
      >
        <!-- 头像 -->
        <div class="flex-shrink-0 mt-1">
          <div v-if="m.role === 'system'" class="w-10 h-10 rounded-full bg-yellow-500/20 flex items-center justify-center text-yellow-500">
            <Settings class="w-6 h-6" />
          </div>
          <ModernAvatar 
            v-else
            :src="getMessageAvatar(m)"
            :name="getMessageLabel(m)"
            :size="40"
            aspect="1"
            object-fit="contain"
            rounded="rounded-xl"
            class="shadow-sm bg-black/20"
          />
        </div>

        <!-- 消息体 -->
        <div class="flex flex-col max-w-[85%] min-w-0" :class="m.role === 'user' ? 'items-end' : 'items-start'">
          <div class="flex items-center gap-2 mb-1 px-1">
            <span class="text-xs font-bold" :class="m.role === 'user' ? 'text-brand-300' : 'text-gray-400'">
              {{ getMessageLabel(m) }}
            </span>
            <span v-if="m.role === 'system'" class="text-[10px] bg-yellow-500/10 text-yellow-500 px-1.5 py-0.5 rounded">SYSTEM</span>
          </div>

          <!-- 气泡 -->
          <div 
            class="message-bubble relative px-5 py-3.5 rounded-2xl text-[15px] leading-7 shadow-sm transition-all duration-200 border max-w-full min-w-0"
            :class="[
              m.role === 'user' 
                ? 'bg-brand/20 backdrop-blur-sm border-brand/20 text-gray-100 rounded-tr-sm hover:border-brand/30' 
                : m.role === 'assistant'
                  ? 'bg-white/5 backdrop-blur-md border-white/10 text-gray-200 rounded-tl-sm hover:bg-white/10'
                  : 'bg-yellow-500/10 border-yellow-500/20 text-gray-300',
            ]"
          >
            <div
              class="md prose prose-invert prose-sm max-w-none prose-p:my-1 prose-headings:my-2 prose-pre:bg-black/30 prose-pre:border prose-pre:border-white/5"
              :style="messageContentFontSizeStyle"
              :ref="(el) => emit('set-content-ref', m.id, el as HTMLElement | null)"
            >
              <div class="stream-markdown" v-html="renderMarkdown(getDisplayContent(m))"></div>
            </div>
            <!-- 长期记忆已保存标记：不受消息字体大小设置影响 -->
            <div
              v-if="m.memoryUpdatedAfterThis"
              class="absolute right-2 bottom-2 flex items-center gap-1 pointer-events-none"
              style="font-size: 10px; line-height: 1;"
            >
              <span class="w-1.5 h-1.5 rounded-full bg-green-500 shrink-0" aria-hidden="true"></span>
              <span class="text-gray-400" style="font-size: 10px;">已保存</span>
            </div>
          </div>

          <!-- 版本切换箭头 -->
          <div v-if="m.role === 'assistant' && hasMultipleVersions(m)" class="flex items-center justify-center gap-2 mt-1 px-1">
            <button 
              class="text-xs text-gray-500 hover:text-gray-300 transition-colors px-2 py-0.5 rounded hover:bg-white/5"
              @click="emit('switch-previous-version', m)"
              :title="`上一个版本 (${getCurrentVersionIndex(m) + 1}/${getVersionCount(m)})`"
            >
              <ChevronLeft class="w-3 h-3" />
            </button>
            <span class="text-xs text-gray-500">
              {{ getCurrentVersionIndex(m) + 1 }}/{{ getVersionCount(m) }}
            </span>
            <button 
              class="text-xs text-gray-500 hover:text-gray-300 transition-colors px-2 py-0.5 rounded hover:bg-white/5"
              @click="emit('switch-next-version', m)"
              :title="`下一个版本 (${getCurrentVersionIndex(m) + 1}/${getVersionCount(m)})`"
            >
              <ChevronRight class="w-3 h-3" />
            </button>
          </div>

          <!-- 底部操作栏 -->
          <div class="flex items-center gap-2 mt-1 px-1 transition-opacity opacity-0 group-hover:opacity-100">
            <button 
              v-if="m.role === 'assistant' && !m.id.startsWith('local_')" 
              class="text-xs text-gray-600 hover:text-blue-400 transition-colors" 
              @click="emit('rewrite-message', m)" 
              :disabled="isGenerating"
            >
              重写
            </button>
            <button 
              class="text-xs text-gray-600 hover:text-brand transition-colors" 
              @click="emit('edit-message', m)" 
              :disabled="isGenerating"
            >
              编辑
            </button>
            <button 
              class="text-xs text-gray-600 hover:text-red-400 transition-colors" 
              :disabled="isGenerating"
              @click="confirmDelete(m, $event)"
            >
              删除
            </button>
          </div>
        </div>
      </div>
    </div>
    
    <!-- 删除确认弹窗 -->
    <ConfirmPopover
      :show="!!deleteConfirm"
      :target="deleteConfirm?.target || null"
      message="确定删除这条消息？"
      confirm-text="删除"
      @confirm="handleConfirmDelete"
      @cancel="cancelDelete"
      @update:show="(val) => !val && cancelDelete()"
    />
  </div>
</template>

<style scoped>
.custom-scrollbar::-webkit-scrollbar {
  width: 4px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 2px;
}
.custom-scrollbar:hover::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.2);
}

/* Markdown 内容样式 */
.md :deep(p) {
  margin-bottom: 0.5em;
  margin-top: 0.5em;
}
.md :deep(p:first-child) {
  margin-top: 0;
}
.md :deep(p:last-child) {
  margin-bottom: 0;
}
.md :deep(a) {
  color: #a78bfa;
  text-decoration: underline;
}

.message-bubble .md {
  width: 100%;
}
.message-bubble .md .stream-markdown {
  overflow: hidden;
  word-wrap: break-word;
}
.message-bubble .md :deep(pre) {
  overflow-x: auto;
  max-width: 100%;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.2) transparent;
}
.message-bubble .md :deep(pre)::-webkit-scrollbar {
  height: 6px;
}
.message-bubble .md :deep(pre)::-webkit-scrollbar-track {
  background: transparent;
}
.message-bubble .md :deep(pre)::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.15);
  border-radius: 3px;
}
.message-bubble .md :deep(pre):hover::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.25);
}
.message-bubble .md :deep(pre code) {
  display: block;
  white-space: pre;
}
.message-bubble .md :deep(code) {
  word-break: break-word;
}
</style>
