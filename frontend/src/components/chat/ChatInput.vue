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
 * - isInterjecting: 是否正在单次回应（插话）中
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
 * - trigger-interject: 触发单次回应（插话），传递角色ID
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
import { useAssistantFabPosition } from '../../composables/useAssistantFabPosition'
import { notifyMessage } from '../../composables/useNotify'
import {
  MAIN_LAYOUT_TRANSITION_MS,
  HEADER_LIFT_EASE,
  HEADER_LIFT_MS,
  type HeaderMorphPhase,
} from '../../constants/chatHeaderMorph'
import type { CharacterCard, GroupMemberSettings } from '../../types/models'
import { validateFilesForTarget } from '../../utils/attachmentPolicy'
import { resolveRichPaste } from '../../utils/richPaste'
import ModernAvatar from '../ModernAvatar.vue'
import ModernSelect from '../ModernSelect.vue'
import { ImagePlus, MessageSquare, PenSquare, RefreshCw, X } from 'lucide-vue-next'

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

const props = withDefaults(
  defineProps<{
  /** 主内容区左缘（视口坐标），用于助手 FAB 左贴边 */
  contentAreaLeftPx?: number
  /** 助手 FAB 允许的最小 top（视口 px），一般为顶栏下缘 + 间距 */
  assistantFabMinTopPx?: number
  /** 非拖动导致的助手 FAB 位置持久化后（窗口、minTop 等），供与 TTS FAB 碰撞分离 */
  onAssistantFabLayout?: () => void
  /** 用户拖动助手 FAB 松手后：只移动助手以消除重叠，TTS 保持不动 */
  onAssistantFabDragEnd?: () => void
  /** 左右贴边 snap 结束后（与 onDragEnd 配合，保证贴边后再判碰撞） */
  onAssistantFabSnapEnd?: () => void
  /** 侧栏是否收起（与顶栏 morph 联动） */
  sidebarCollapsed?: boolean
  /** 顶栏变形阶段：与 ChatPage headerMorphPhase 一致 */
  headerMorphPhase?: HeaderMorphPhase
  // 输入状态
  modelValue: string
  isGenerating: boolean
  streamError: string | null
  draftImages: DraftImagePreview[]
  draftHelperStatus: 'reasoning' | 'writing' | 'done' | null
  
  // 群聊相关
  isGroup: boolean
  groupMembers: CharacterCard[]
  currentSpeakerIndex: number
  isPaused: boolean
  showContinueButton: boolean
  pendingMembersCount: number
  canInterject: boolean
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
  }>(),
  {
    sidebarCollapsed: false,
    headerMorphPhase: 'inset',
  }
)

const emit = defineEmits<{
  'update:modelValue': [value: string]
  'send': []
  'primary-action': []
  'pause-group': []
  'continue-group': []
  'trigger-interject': [characterId: string]
  'select-model': [option: any]
  'toggle-assistant': []
  'select-images': [files: File[]]
  'remove-image': [imageId: string]
  'open-draft-helper': [mode: 'write' | 'enhance']
  'draft-helper-stop': []
  'draft-helper-keep': []
  'draft-helper-rewrite': []
  'draft-helper-discard': []
}>()

const imageInputRef = ref<HTMLInputElement | null>(null)
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const showDraftHelperMenu = ref(false)
/** 碰撞检测用真实视口矩形（与 CSS 过渡中的 topPx 解耦） */
const assistantFabButtonRef = ref<HTMLElement | null>(null)

const {
  fabStyle,
  setTopPxFromSeparation: setAssistantTopPxFromSeparation,
  onPointerDown: assistantFabPointerDown,
  onPointerMove: assistantFabPointerMove,
  onPointerUp: assistantFabPointerUp,
  onPointerCancel: assistantFabPointerCancel,
  onFabClick: assistantFabOnClick,
} = useAssistantFabPosition(
  () => props.contentAreaLeftPx ?? 0,
  () => props.assistantFabMinTopPx ?? 0,
  {
    onLayoutStable: () => props.onAssistantFabLayout?.(),
    onDragEnd: () => props.onAssistantFabDragEnd?.(),
    onSnapEnd: () => props.onAssistantFabSnapEnd?.(),
  },
)

function onAssistantFabClick(e: MouseEvent) {
  if (assistantFabOnClick(e)) return
  emit('toggle-assistant')
}

/**
 * 计算是否有草稿消息
 *
 * 检查输入框是否有非空内容。
 */
const hasDraftMessage = computed(() => !!props.modelValue.trim() || props.draftImages.length > 0)

/** 群聊左侧：整轮发言中 / 暂停续聊 / 单次回应中 → 显示轮次状态；否则空闲时可显示点头像 */
const groupShowsRoundStatus = computed(() => {
  if (!props.isGroup) return false
  if (props.isGenerating && props.currentSpeakerIndex >= 0) return true
  if (props.showContinueButton && props.pendingMembersCount > 0) return true
  if (props.isInterjecting) return true
  return false
})

/**
 * 计算主要操作按钮标签
 *
 * 根据当前状态（流式传输、继续按钮、群聊等）返回相应的按钮标签。
 */
const primaryActionLabel = computed(() => {
  if (props.isStreamingActive) return '停止'
  if (props.showContinueButton && props.isGroup) {
    return hasDraftMessage.value ? '发送' : '继续轮次'
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
    return '输入消息或点头像单次回应，或点击继续轮次...'
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
    void handleIncomingMainChatFiles(files)
  }
  input.value = ''
}

async function handleIncomingMainChatFiles(files: File[]) {
  const { accepted, rejected } = validateFilesForTarget(files, 'main-chat')
  if (rejected.some((item) => item.reason === 'unsupported')) {
    await notifyMessage('主聊天暂仅支持图片。', { title: '提示' })
  }
  if (rejected.some((item) => item.reason === 'too-large')) {
    await notifyMessage('主聊天图片单文件不能超过 100MB。', { title: '附件过大' })
  }
  if (accepted.length) {
    emit('select-images', accepted.map((item) => item.file))
  }
}

/**
 * 在光标处插入文本（用于粘贴图文混排时的文字部分）
 */
function insertTextAtCursor(text: string) {
  const el = textareaRef.value
  if (!el) {
    emit('update:modelValue', props.modelValue + text)
    return
  }
  const start = el.selectionStart
  const end = el.selectionEnd
  const current = props.modelValue
  const newValue = current.slice(0, start) + text + current.slice(end)
  emit('update:modelValue', newValue)
  // 恢复光标到插入内容之后
  setTimeout(() => {
    const pos = start + text.length
    el.setSelectionRange(pos, pos)
    el.focus()
  }, 0)
}

/**
 * 处理粘贴：支持从剪贴板粘贴图片，以及图片+文字混排一次性粘贴。
 * 解析逻辑已抽到 shared richPaste util；主聊天这里额外套一层图片白名单。
 */
async function handlePaste(e: ClipboardEvent) {
  const resolved = await resolveRichPaste(e.clipboardData)
  if (!resolved) return
  if (resolved.files.length > 0 || resolved.text) {
    e.preventDefault()
  }
  if (resolved.files.length > 0) {
    await handleIncomingMainChatFiles(resolved.files)
  }
  if (resolved.text) {
    insertTextAtCursor(resolved.text)
  }
}

function handleInput(e: Event) {
  const target = e.target as HTMLTextAreaElement | null
  emit('update:modelValue', target?.value ?? '')
}

function toggleDraftHelperMenu() {
  showDraftHelperMenu.value = !showDraftHelperMenu.value
}

function triggerDraftHelper(mode: 'write' | 'enhance') {
  showDraftHelperMenu.value = false
  emit('open-draft-helper', mode)
}

const draftHelperStatusText = computed(() => {
  if (props.draftHelperStatus === 'reasoning') return '思考中'
  if (props.draftHelperStatus === 'writing') return '写作中'
  if (props.draftHelperStatus === 'done') return '已完成'
  return ''
})

const isDraftHelperRunning = computed(() => {
  return props.draftHelperStatus === 'reasoning' || props.draftHelperStatus === 'writing'
})

/** 侧栏收起且顶栏已过 inset，进入 lifting/full 时下沉并盖住底部提示 */
const sinkMorphed = computed(
  () =>
    props.sidebarCollapsed &&
    (props.headerMorphPhase === 'lifting' || props.headerMorphPhase === 'full')
)

/** 与 inputPlaceholder 默认「发送消息...」分支一致，用于叠层占位与遮罩 */
const isDefaultPlaceholderVariant = computed(() => {
  if (props.isGenerating && props.isGroup && !props.isPaused) return false
  if (props.showContinueButton) return false
  return true
})

const ENHANCED_PLACEHOLDER_TEXT = 'Ctrl + Enter 发送消息...'

const showPlaceholderReveal = computed(
  () =>
    sinkMorphed.value &&
    !props.modelValue.trim() &&
    !inputDisabled.value &&
    isDefaultPlaceholderVariant.value &&
    !props.draftHelperStatus
)

/** 与顶栏 lifting / 展开回弹共用时长与曲线（供子元素 transition 使用） */
const morphCssVars = computed(() => {
  if (!props.sidebarCollapsed) {
    return {
      '--chat-input-trans-dur': `${MAIN_LAYOUT_TRANSITION_MS}ms`,
      '--chat-input-trans-ease': 'ease',
    } as Record<string, string>
  }
  if (sinkMorphed.value) {
    return {
      '--chat-input-trans-dur': `${HEADER_LIFT_MS}ms`,
      '--chat-input-trans-ease': HEADER_LIFT_EASE,
    } as Record<string, string>
  }
  return {
    '--chat-input-trans-dur': '320ms',
    '--chat-input-trans-ease': 'ease',
  } as Record<string, string>
})

/** 与叠层可见文案一致，并补充底部提示中的 Markdown 说明，供读屏 */
const textareaAriaLabel = computed(() => {
  if (showPlaceholderReveal.value) {
    return `${ENHANCED_PLACEHOLDER_TEXT} Markdown 支持。`
  }
  return inputPlaceholder.value
})

const textareaPlaceholderAttr = computed(() =>
  showPlaceholderReveal.value ? '' : inputPlaceholder.value
)

/** 顶栏 morph 变量挂在输入壳上，子树继承；与下沉负 margin 共用 transition */
const shellInlineStyle = computed(() => ({
  color: 'rgba(229, 231, 235, 1)',
  backgroundColor: 'unset',
  background: 'unset',
  opacity: 1,
  ...morphCssVars.value,
}))

function getAssistantFabRect(): DOMRect | null {
  return assistantFabButtonRef.value?.getBoundingClientRect() ?? null
}

defineExpose({ getAssistantFabRect, setAssistantTopPx: setAssistantTopPxFromSeparation })
</script>

<template>
  <div
    class="chat-input-shell shrink-0 px-4 pb-6 pt-0 w-full max-w-4xl mx-auto z-20 relative overflow-visible"
    :class="{ 'chat-input-shell--sink': sinkMorphed }"
    :style="shellInlineStyle"
  >
    <div class="chat-input-morph-wrap relative">
    <!-- 
      Refactored Container:
      - Uses bg-slate-900/70 and backdrop-blur-xl for strong glass effect
      - Uses border-white/10 for subtle border
      - Removed hardcoded hex colors
    -->
    <div
      class="chat-input-card-morph relative z-10 bg-surface-overlay backdrop-blur-xl border border-[var(--color-border)] rounded-2xl shadow-xl p-3 flex flex-col gap-2 focus-within:border-brand-a40 focus-within:ring-1 focus-within:ring-brand-a20 focus-within:bg-surface-overlay"
      :class="{ 'chat-input-card--sink': sinkMorphed }"
      style="opacity: 1;"
    >
      <div v-if="draftHelperStatus" class="flex items-center justify-between gap-3 px-3 py-2 rounded-lg bg-[var(--color-border-subtle)] border border-[var(--color-border)]">
        <div class="text-xs text-[var(--color-text-secondary)] min-w-0">{{ draftHelperStatusText }}</div>
        <button
          v-if="isDraftHelperRunning"
          class="btn btn-xs btn-secondary border border-[var(--color-error)]/20 bg-[var(--color-error-bg)] text-[var(--color-error)] hover:opacity-90"
          @click="emit('draft-helper-stop')"
        >
          终止
        </button>
        <div v-if="draftHelperStatus === 'done'" class="flex items-center gap-2">
          <button class="btn btn-xs btn-secondary" @click="emit('draft-helper-keep')">保留</button>
          <button class="btn btn-xs btn-secondary" @click="emit('draft-helper-rewrite')">
            <RefreshCw class="w-3 h-3" />
            重写
          </button>
          <button class="btn btn-xs btn-secondary" @click="emit('draft-helper-discard')">放弃</button>
        </div>
      </div>
      <div class="relative min-h-[80px]">
      <textarea
        ref="textareaRef"
        :value="modelValue"
        @input="handleInput"
        @paste="handlePaste"
        :placeholder="textareaPlaceholderAttr"
        :aria-label="textareaAriaLabel"
        :disabled="inputDisabled"
        class="input textarea !bg-transparent !border-0 text-base resize-none min-h-[80px] w-full text-primary placeholder-gray-500"
        :class="inputDisabled ? 'opacity-50' : ''"
        @keydown="handleKeydown"
      ></textarea>
      <div
        v-if="showPlaceholderReveal"
        class="chat-input-placeholder-layer pointer-events-none absolute inset-0 box-border overflow-hidden text-left"
        aria-hidden="true"
      >
        <span class="chat-input-placeholder-reveal text-base leading-normal text-gray-500">{{ ENHANCED_PLACEHOLDER_TEXT }}</span>
      </div>
      </div>

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
      
      <div class="flex items-center justify-between gap-2 pt-2 border-t border-[var(--color-border-subtle)]">
          <div class="flex-1 min-w-0 h-8 flex items-center gap-2 overflow-x-auto">
            <!-- 轮次 / 输出中：状态条 -->
            <template v-if="groupShowsRoundStatus">
              <div v-if="isGroup && isGenerating && currentSpeakerIndex >= 0" class="flex items-center gap-2 text-xs text-[var(--color-purple)] shrink-0">
                <span class="animate-pulse">●</span>
                <span>{{ groupMembers[currentSpeakerIndex]?.name || '角色' }} 正在发言...</span>
                <span class="text-[var(--color-text-muted)]">({{ currentSpeakerIndex + 1 }}/{{ groupMembers.length }})</span>
                <button 
                  class="ml-1 px-2 py-0.5 text-xs bg-[var(--color-warning-bg)] hover:opacity-90 text-[var(--color-warning)] rounded transition-colors border border-[var(--color-warning)]/20"
                  @click="emit('pause-group')"
                >
                  暂停
                </button>
              </div>
              <div v-else-if="showContinueButton && pendingMembersCount > 0" class="flex items-center gap-2 text-xs text-green-400 shrink-0">
                <span class="truncate">轮次已暂停，还有 {{ pendingMembersCount }} 位角色待发言</span>
                <button 
                  class="px-2 py-0.5 text-xs bg-green-500/20 hover:bg-green-500/30 text-green-400 rounded transition-colors font-medium border border-green-500/20 shrink-0"
                  @click="emit('continue-group')"
                >
                  继续轮次
                </button>
              </div>
              <div v-else-if="isGroup && isInterjecting" class="flex items-center gap-2 text-xs text-[var(--color-purple)] shrink-0">
                <span class="animate-pulse">●</span>
                <span>角色单次回应中...</span>
              </div>
            </template>
            <!-- 空闲：点头像单次回应（与上方互斥，省一行空间） -->
            <template v-else-if="isGroup && canInterject">
              <span class="text-[var(--color-purple)] flex items-center gap-1 shrink-0 text-xs">
                <MessageSquare class="w-3 h-3" /> 单次：
              </span>
              <div class="flex items-center gap-0.5 flex-wrap min-w-0">
                <div
                  v-for="member in groupMembers"
                  :key="member.id"
                  class="cursor-pointer hover:scale-110 transition-transform shrink-0"
                  :title="`让 ${member.name} 单次回应一条`"
                  @click="emit('trigger-interject', member.id)"
                >
                  <ModernAvatar
                    :src="member.avatar ? `/api/avatars/${member.avatar}` : null"
                    :name="member.name"
                    :size="22"
                    aspect="1"
                    rounded="rounded-lg"
                    class="ring-2 ring-purple-500/50 hover:ring-purple-500"
                  />
                </div>
              </div>
            </template>
          </div>
          
          <div class="flex items-center gap-3 shrink-0">
          <div class="relative">
            <button
              class="chat-action-button chat-action-button--secondary shadow-lg transition-all active:scale-95"
              :disabled="isGenerating && !showContinueButton"
              @click="toggleDraftHelperMenu"
              title="写作辅助"
            >
              <PenSquare class="w-4 h-4" />
            </button>
            <div
              v-if="showDraftHelperMenu"
              class="draft-helper-menu absolute right-0 bottom-full mb-2 w-56 rounded-lg border border-[var(--color-border)] bg-surface-overlay p-2 shadow-xl z-30"
            >
              <button class="w-full text-left px-2 py-1.5 text-sm text-[var(--color-text)] rounded hover:bg-surface-muted" @click="triggerDraftHelper('write')">
                帮我写点什么
              </button>
              <button class="w-full text-left px-2 py-1.5 text-sm text-[var(--color-text)] rounded hover:bg-surface-muted" @click="triggerDraftHelper('enhance')">
                润色并扩写我的草稿
              </button>
            </div>
          </div>
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

    <div
      class="chat-input-footer-hint relative z-0 text-center mt-2 text-xs text-[var(--color-text-muted)] pointer-events-none"
      :class="sinkMorphed ? 'opacity-0' : 'opacity-100'"
    >
      Markdown 支持 · Ctrl + Enter 发送
    </div>
    </div>
    
    <!-- 助手按钮（可拖动，松手左右贴边，位置持久化） -->
    <button
      ref="assistantFabButtonRef"
      type="button"
      class="chat-fab-surface w-12 h-12 rounded-xl font-bold shadow-lg transition-[transform,background-color,box-shadow] border border-[var(--color-border)] hover:scale-105 active:scale-95 flex items-center justify-center backdrop-blur-sm cursor-grab active:cursor-grabbing"
      :style="fabStyle"
      @pointerdown="assistantFabPointerDown"
      @pointermove="assistantFabPointerMove"
      @pointerup="assistantFabPointerUp"
      @pointercancel="assistantFabPointerCancel"
      @click="onAssistantFabClick"
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

/* 与 forms.css .input 内边距一致，叠层起点与原生 placeholder 对齐 */
.chat-input-placeholder-layer {
  padding: 0.5rem 0.75rem;
}

/*
 * 下沉：transform 不占布局，会在壳顶留下与 translateY 等高的空隙。
 * 外壳用等量负 margin-top 上移，与卡片下移相抵，消除与消息区之间的多余缝，且不挤占 flex-1 列表高度。
 * margin 的 transition 必须挂在壳基类上：仅写在 --sink 上时，侧栏展开去掉类后元素失去 transition，margin 会瞬间归零而 transform 仍在过渡，造成底部「截断」感。
 * --chat-input-sink-shift：卡片下移与壳负 margin 必须同值；略大于原 1.125rem，以盖住底部提示行（mt-2 + text-xs）并略有余量。
 */
.chat-input-shell {
  --chat-input-sink-shift: 1.75rem;
  margin-top: 0;
  transition: margin-top var(--chat-input-trans-dur, 320ms) var(--chat-input-trans-ease, ease);
}

.chat-input-shell--sink {
  margin-top: calc(-1 * var(--chat-input-sink-shift));
}

.chat-input-card-morph {
  transition:
    transform var(--chat-input-trans-dur, 320ms) var(--chat-input-trans-ease, ease),
    border-color 200ms ease,
    box-shadow 200ms ease,
    background-color 200ms ease;
}

.chat-input-card--sink {
  transform: translateY(var(--chat-input-sink-shift));
}

.chat-input-footer-hint {
  transition: opacity var(--chat-input-trans-dur, 320ms) var(--chat-input-trans-ease, ease);
}

@keyframes chatInputPlaceholderLtr {
  from {
    clip-path: inset(0 100% 0 0);
  }
  to {
    clip-path: inset(0 0 0 0);
  }
}

.chat-input-placeholder-reveal {
  animation: chatInputPlaceholderLtr var(--chat-input-trans-dur, 420ms) var(--chat-input-trans-ease, cubic-bezier(0.45, 0.05, 0.55, 0.95)) forwards;
}

@media (prefers-reduced-motion: reduce) {
  .chat-input-shell {
    transition: none !important;
  }
  .chat-input-shell--sink {
    margin-top: 0 !important;
  }
  .chat-input-card-morph {
    transition: border-color 200ms ease, box-shadow 200ms ease, background-color 200ms ease !important;
  }
  .chat-input-card--sink {
    transform: none !important;
  }
  .chat-input-footer-hint {
    transition: none !important;
  }
  .chat-input-placeholder-reveal {
    animation: none !important;
    clip-path: none !important;
  }
}

.draft-helper-menu {
  backdrop-filter: blur(var(--blur-light));
  -webkit-backdrop-filter: blur(var(--blur-light));
}
</style>
