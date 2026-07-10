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
import { useAssistantFabPosition, ASSISTANT_FAB_SIZE, ASSISTANT_FAB_GAP } from '../../composables/useAssistantFabPosition'
import { notifyMessage } from '../../composables/useNotify'
import {
  MAIN_LAYOUT_TRANSITION_MS,
  HEADER_LIFT_EASE,
  HEADER_LIFT_MS,
  TTS_TOP_BAR_TWO_BTN_STACK_PX,
  TOP_BAR_AGENT_AFTER_TTS_GAP_PX,
  type HeaderMorphPhase,
} from '../../constants/chatHeaderMorph'
import type { CharacterCard, GroupMemberSettings } from '../../types/models'
import { validateFilesForTarget } from '../../utils/attachmentPolicy'
import { resolveRichPaste } from '../../utils/richPaste'
import ModernAvatar from '../ModernAvatar.vue'
import ModernSelect from '../ModernSelect.vue'
import SelectDropdownSurface from '../SelectDropdownSurface.vue'
import { useMvuStore } from '../../stores/mvu'
import {
  Check,
  Globe,
  ImagePlus,
  MessageSquare,
  MoreHorizontal,
  PenSquare,
  RefreshCw,
  Sparkles,
  X,
} from 'lucide-vue-next'

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
  /** 与 useViewportNarrowPortrait 一致（约 &lt; 10/16）：工具行压缩，模型下拉可 shrink */
  isNarrowPortrait?: boolean
  /** 顶栏变形阶段：与 ChatPage headerMorphPhase 一致 */
  headerMorphPhase?: HeaderMorphPhase
  /** 侧栏收起且顶栏 squeeze 完成后：顶栏下显示 Agent 胶囊（与 TTS 顶栏条时机一致） */
  showAgentTopBarControls?: boolean
  /** 全局 TTS 是否启用（决定 Agent 顶栏是否让位给队列/播放） */
  ttsEnabled?: boolean
  /** TTS 顶栏替代控件是否已显示（仅当 ttsEnabled 时为 true） */
  ttsTopBarControlsVisible?: boolean
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
  
  /** 主聊天网络搜索开关：为 true 时每次发送均在服务端挂载搜索工具，直至用户关闭 */
  webSearchEnabled?: boolean
  
  // 辅助函数
  getMemberSettings: (memberId: string) => GroupMemberSettings
  }>(),
  {
    sidebarCollapsed: false,
    isNarrowPortrait: false,
    headerMorphPhase: 'inset',
    showAgentTopBarControls: false,
    ttsEnabled: false,
    ttsTopBarControlsVisible: false,
    webSearchEnabled: false,
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
  'toggle-mvu-panel': []
  'focus-assistant-panel': []
  'update:webSearchEnabled': [value: boolean]
}>()

const mvuStore = useMvuStore()
const imageInputRef = ref<HTMLInputElement | null>(null)
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const showDraftHelperMenu = ref(false)
const showComposerOverflowMenu = ref(false)
/** SelectDropdownSurface 定位锚点（relative 包裹触发按钮） */
const draftHelperMenuAnchorRef = ref<HTMLElement | null>(null)
const composerOverflowMenuAnchorRef = ref<HTMLElement | null>(null)

const isDragOverComposer = ref(false)
/** 碰撞检测用真实视口矩形（与 CSS 过渡中的 topPx 解耦） */
const assistantFabStackRef = ref<HTMLElement | null>(null)
const assistantFabButtonRef = ref<HTMLButtonElement | null>(null)

const {
  fabStyle,
  side,
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
    getDragReferenceRect: () => assistantFabButtonRef.value?.getBoundingClientRect() ?? null,
    getInputSinkActive: () =>
      props.sidebarCollapsed &&
      (props.headerMorphPhase === 'lifting' || props.headerMorphPhase === 'full'),
    getFabStackHeight: () =>
      mvuStore.isConnected
        ? ASSISTANT_FAB_SIZE + ASSISTANT_FAB_GAP + ASSISTANT_FAB_SIZE
        : ASSISTANT_FAB_SIZE,
  },
)

function onAssistantFabClick(e: MouseEvent) {
  if (assistantFabOnClick(e)) return
  emit('toggle-assistant')
}

function onMvueFabClick(e: MouseEvent) {
  if (assistantFabOnClick(e)) return
  emit('toggle-mvu-panel')
}

function toggleWebSearch() {
  emit('update:webSearchEnabled', !props.webSearchEnabled)
}

function openImagePickerFromOverflow() {
  showComposerOverflowMenu.value = false
  openImagePicker()
}

function toggleComposerOverflowMenu() {
  showComposerOverflowMenu.value = !showComposerOverflowMenu.value
  if (showComposerOverflowMenu.value) {
    showDraftHelperMenu.value = false
  }
}

function onAgentTopBarClick(e: MouseEvent) {
  e.stopPropagation()
  emit('focus-assistant-panel')
}

const agentTopBarStackStyle = computed(() => {
  const minTop = props.assistantFabMinTopPx ?? 0
  const underTts =
    props.ttsEnabled && props.ttsTopBarControlsVisible
      ? TTS_TOP_BAR_TWO_BTN_STACK_PX + TOP_BAR_AGENT_AFTER_TTS_GAP_PX
      : 0
  const top = `${minTop + underTts}px`
  const leftBase = props.contentAreaLeftPx ?? 0
  if (side.value === 'left') {
    return {
      top,
      left: `${leftBase + 8}px`,
      right: 'auto' as const,
    }
  }
  return {
    top,
    right: '16px',
    left: 'auto' as const,
  }
})

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
    return '下一轮'
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

function handleDragEnter(event: DragEvent) {
  if (inputDisabled.value) return
  if (!event.dataTransfer?.types.includes('Files')) return
  isDragOverComposer.value = true
}

function handleDragLeave(event: DragEvent) {
  const nextTarget = event.relatedTarget as Node | null
  if (nextTarget && (event.currentTarget as HTMLElement | null)?.contains(nextTarget)) return
  isDragOverComposer.value = false
}

function handleDragOver(event: DragEvent) {
  if (!event.dataTransfer?.types.includes('Files')) return
  event.preventDefault()
  if (!inputDisabled.value) {
    isDragOverComposer.value = true
  }
}

async function handleDrop(event: DragEvent) {
  const files = Array.from(event.dataTransfer?.files || [])
  isDragOverComposer.value = false
  if (!files.length) return
  event.preventDefault()
  if (inputDisabled.value) return
  await handleIncomingMainChatFiles(files)
}

function handleInput(e: Event) {
  const target = e.target as HTMLTextAreaElement | null
  emit('update:modelValue', target?.value ?? '')
}

function toggleDraftHelperMenu() {
  showDraftHelperMenu.value = !showDraftHelperMenu.value
  if (showDraftHelperMenu.value) {
    showComposerOverflowMenu.value = false
  }
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

  /** 顶栏 morph 变量挂在输入壳上，子树继承；下沉 = morph-wrap translateY + 壳等量负 margin（布局补偿） */
const shellInlineStyle = computed(() => ({
  color: 'var(--color-text)',
  backgroundColor: 'unset',
  background: 'unset',
  opacity: 1,
  ...morphCssVars.value,
}))

function getAssistantFabRect(): DOMRect | null {
  return assistantFabStackRef.value?.getBoundingClientRect() ?? null
}

function focusComposer() {
  textareaRef.value?.focus()
}

defineExpose({
  getAssistantFabRect,
  setAssistantTopPx: setAssistantTopPxFromSeparation,
  focusComposer,
})
</script>

<template>
  <div
    class="chat-input-shell pointer-events-none shrink-0 px-4 pb-6 pt-0 w-full max-w-4xl mx-auto z-40 relative overflow-visible"
    :class="{ 'chat-input-shell--sink': sinkMorphed }"
    :style="shellInlineStyle"
  >
    <div class="chat-input-morph-wrap pointer-events-auto relative">
    <div
      class="chat-input-float-stack relative z-10"
    >
    <!-- 主输入区使用统一 surface-panel 玻璃层级，具体背景/模糊/边框由样式基座控制。 -->
    <div
      class="chat-input-card-morph surface-panel relative z-0 p-3 flex flex-col gap-2 focus-within:border-brand-a40 focus-within:ring-1 focus-within:ring-[var(--color-focus-ring)]"
      style="opacity: 1;"
      @dragenter.prevent="handleDragEnter"
      @dragover.prevent="handleDragOver"
      @dragleave="handleDragLeave"
      @drop.prevent="handleDrop"
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
        class="input textarea !bg-transparent !border-0 text-base resize-none min-h-[80px] w-full text-primary placeholder:text-muted"
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
            type="button"
            class="icon-button absolute top-1 right-1 w-5 h-5 rounded-full bg-[var(--color-overlay-heavy)] text-[var(--color-text)]"
            aria-label="移除图片"
            @click="emit('remove-image', img.id)"
          >
            <X class="w-3 h-3" />
          </button>
        </div>
      </div>
      
      <div class="flex min-w-0 items-center justify-between gap-2 pt-2 border-t border-[var(--color-border-subtle)]">
          <div class="flex-1 min-w-0 h-8 flex items-center gap-2 overflow-x-auto">
            <!-- 轮次 / 输出中：状态条 -->
            <template v-if="groupShowsRoundStatus">
              <div v-if="isGroup && isGenerating && currentSpeakerIndex >= 0" class="flex items-center gap-2 text-xs text-[var(--color-purple)] shrink-0">
                <span class="animate-pulse">●</span>
                <span>{{ groupMembers[currentSpeakerIndex]?.name || '角色' }} 正在发言...</span>
                <span class="text-[var(--color-text-muted)]">({{ currentSpeakerIndex + 1 }}/{{ groupMembers.length }})</span>
                <button 
                  type="button"
                  class="btn btn-xs btn-secondary text-warning"
                  @click="emit('pause-group')"
                >
                  暂停
                </button>
              </div>
              <div v-else-if="showContinueButton && pendingMembersCount > 0" class="flex items-center gap-2 text-xs text-success shrink-0">
                <span class="truncate">轮次已暂停，还有 {{ pendingMembersCount }} 位角色待发言</span>
                <button 
                  type="button"
                  class="btn btn-xs btn-success shrink-0"
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
                  role="button"
                  tabindex="0"
                  :aria-label="`让 ${member.name} 单次回应一条`"
                  @click="emit('trigger-interject', member.id)"
                  @keydown.enter.prevent="emit('trigger-interject', member.id)"
                  @keydown.space.prevent="emit('trigger-interject', member.id)"
                >
                  <ModernAvatar
                    :src="member.avatar ? `/api/avatars/${member.avatar}` : null"
                    :name="member.name"
                    :size="22"
                    aspect="1"
                    rounded="rounded-lg"
                    class="ring-2 ring-[var(--color-brand-a30)] hover:ring-[var(--color-brand-a50)]"
                  />
                </div>
              </div>
            </template>
          </div>
          
          <div class="flex min-w-0 shrink items-center gap-3">
          <div class="flex items-center gap-0 shrink-0">
          <div ref="draftHelperMenuAnchorRef" class="relative">
            <button
              class="chat-action-button chat-action-button--secondary shadow-lg transition-[transform,box-shadow] active:scale-95"
              :disabled="isGenerating && !showContinueButton"
              aria-label="写作辅助"
              @click="toggleDraftHelperMenu"
            >
              <PenSquare class="w-4 h-4" />
            </button>
            <SelectDropdownSurface
              v-model:open="showDraftHelperMenu"
              :anchor-ref="draftHelperMenuAnchorRef"
              placement="top"
              :auto-width="true"
              :gap-px="8"
              max-height-class="max-h-[min(320px,calc(100vh-6rem))]"
            >
              <button
                type="button"
                class="w-full text-left px-3 py-2 rounded-lg text-sm cursor-pointer transition-colors text-[var(--color-text-secondary)] hover:bg-surface-muted"
                role="menuitem"
                @click="triggerDraftHelper('write')"
              >
                帮我写点什么
              </button>
              <button
                type="button"
                class="w-full text-left px-3 py-2 rounded-lg text-sm cursor-pointer transition-colors text-[var(--color-text-secondary)] hover:bg-surface-muted"
                role="menuitem"
                @click="triggerDraftHelper('enhance')"
              >
                润色并扩写我的草稿
              </button>
            </SelectDropdownSurface>
          </div>
          <template v-if="!isNarrowPortrait">
          <button
            type="button"
            class="chat-action-button shadow-lg transition-[transform,box-shadow] active:scale-95"
            :class="
              webSearchEnabled
                ? 'bg-brand-a20 text-brand ring-2 ring-[var(--color-brand-a40)] border border-[var(--color-brand-a30)]'
                : 'chat-action-button--secondary'
            "
            :disabled="isGenerating && !showContinueButton"
            aria-label="网络搜索：开启后每次发送启用，直至关闭；需在全局设置配置 Tavily 或博查"
            @click="toggleWebSearch"
          >
            <Globe class="w-4 h-4" />
          </button>
          <button
            class="chat-action-button chat-action-button--secondary shadow-lg transition-[transform,box-shadow] active:scale-95"
            :disabled="isGenerating && !showContinueButton"
            aria-label="选择图片"
            @click="openImagePicker"
          >
            <ImagePlus class="w-4 h-4" />
          </button>
          </template>
          <template v-else>
          <div ref="composerOverflowMenuAnchorRef" class="relative">
            <button
              type="button"
              class="chat-action-button chat-action-button--secondary shadow-lg transition-[transform,box-shadow] active:scale-95"
              :disabled="isGenerating && !showContinueButton"
              aria-label="更多输入选项"
              @click="toggleComposerOverflowMenu"
            >
              <MoreHorizontal class="w-4 h-4" />
            </button>
            <SelectDropdownSurface
              v-model:open="showComposerOverflowMenu"
              :anchor-ref="composerOverflowMenuAnchorRef"
              placement="top"
              :auto-width="true"
              :gap-px="8"
              max-height-class="max-h-[min(320px,calc(100vh-6rem))]"
            >
              <button
                type="button"
                class="w-full px-3 py-2 rounded-lg text-sm cursor-pointer transition-colors flex items-center justify-between gap-2"
                :class="
                  webSearchEnabled
                    ? 'bg-brand-a20 text-brand hover:bg-brand-a30'
                    : 'text-[var(--color-text-secondary)] hover:bg-surface-muted'
                "
                role="menuitem"
                @click="showComposerOverflowMenu = false; toggleWebSearch()"
              >
                <span class="min-w-0 truncate text-left">网络搜索</span>
                <Check v-if="webSearchEnabled" class="w-3 h-3 shrink-0 text-brand" />
              </button>
              <button
                type="button"
                class="w-full text-left px-3 py-2 rounded-lg text-sm cursor-pointer transition-colors text-[var(--color-text-secondary)] hover:bg-surface-muted"
                role="menuitem"
                @click="openImagePickerFromOverflow"
              >
                选择图片
              </button>
            </SelectDropdownSurface>
          </div>
          </template>
          </div>
          <input
            ref="imageInputRef"
            type="file"
            accept="image/*"
            multiple
            class="hidden"
            @change="handleImageInputChange"
          />
          <div class="min-w-0 max-w-[200px] shrink flex-1">
          <ModernSelect
            :model-value="currentModel"
            :selected-preset-id="currentPresetId ?? null"
            :options="modelOptions"
            placement="top"
            placeholder="选择模型 (自动关联预设)..."
            class="!text-xs min-w-[7rem] w-full max-w-[200px]"
            dropdown-width="410"
            searchable
            allow-create
            @select="emit('select-model', $event)"
          />
          </div>
          <button 
            class="chat-action-button shadow-lg transition-[transform,box-shadow] active:scale-95"
            :class="[primaryActionClass, primaryActionDisabled ? 'opacity-50 cursor-not-allowed' : 'hover:shadow-brand hover:-translate-y-0.5']"
            :disabled="primaryActionDisabled"
            @click="emit('primary-action')"
          >
            {{ primaryActionLabel }}
          </button>
          </div>
      </div>
      <div
        v-show="isDragOverComposer"
        class="pointer-events-none absolute inset-0 z-[21] rounded-2xl bg-[var(--color-brand-a20)] ring-1 ring-inset ring-[var(--color-brand-a40)] transition-opacity duration-150"
        aria-hidden="true"
      />
    </div>
    </div>

    <div
      class="chat-input-footer-hint relative z-0 text-center mt-2 text-xs text-[var(--color-text-muted)] pointer-events-none"
      :class="sinkMorphed ? 'opacity-0' : 'opacity-100'"
    >
      Markdown 支持 · Ctrl + Enter 发送
    </div>
    </div>
    
    <!-- 助手 / MVU FAB：侧栏收起顶栏 full 后与 TTS 同相滑出，顶栏下替代为 Agent 胶囊 -->
    <div
      ref="assistantFabStackRef"
      class="assistant-fab-stack pointer-events-auto flex flex-col gap-2"
      :class="{ 'assistant-fab-stack--hidden': showAgentTopBarControls }"
      :style="fabStyle"
    >
      <button
        ref="assistantFabButtonRef"
        type="button"
        class="chat-fab-surface w-12 h-12 rounded-xl font-bold shadow-lg transition-[transform,background-color,box-shadow] border border-[var(--color-border)] hover:scale-105 active:scale-95 flex items-center justify-center cursor-grab active:cursor-grabbing"
        aria-label="打开聊天助手"
        @pointerdown="assistantFabPointerDown"
        @pointermove="assistantFabPointerMove"
        @pointerup="assistantFabPointerUp"
        @pointercancel="assistantFabPointerCancel"
        @click="onAssistantFabClick"
      >
        助手
      </button>

      <button
        v-if="mvuStore.isConnected"
        type="button"
        class="chat-fab-surface w-12 h-12 rounded-xl font-bold shadow-lg transition-[transform,background-color,box-shadow] border border-[var(--color-border)] hover:scale-105 active:scale-95 flex items-center justify-center cursor-grab active:cursor-grabbing"
        aria-label="打开 MVU 工作日志"
        @pointerdown="assistantFabPointerDown"
        @pointermove="assistantFabPointerMove"
        @pointerup="assistantFabPointerUp"
        @pointercancel="assistantFabPointerCancel"
        @click="onMvueFabClick"
      >
        MVU
      </button>
    </div>

    <Transition name="tts-top-bar-fade">
      <div
        v-if="showAgentTopBarControls"
        class="fixed z-[9] flex flex-col gap-2 pointer-events-none"
        :style="agentTopBarStackStyle"
      >
        <div class="pointer-events-auto flex flex-col gap-2">
          <button
            type="button"
            class="agent-top-bar-btn"
            :class="{ 'agent-top-bar-btn--after-tts': ttsEnabled && ttsTopBarControlsVisible }"
            aria-label="打开聊天助手"
            @click="onAgentTopBarClick"
          >
            <span class="agent-top-bar-btn__glow" aria-hidden="true" />
            <Sparkles class="agent-top-bar-btn__icon" aria-hidden="true" />
            <span class="agent-top-bar-btn__label">Agent</span>
          </button>
        </div>
      </div>
    </Transition>
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
 * 下沉：morph-wrap 用 translateY 下移（卡片 + 底部提示同相）；外壳用等量负 margin-top
 * 上移布局，抵消 transform 不占流的空隙，避免与消息列表之间多出 sink-shift。
 * margin 的 transition 必须挂在壳基类上：仅写在 --sink 上时，侧栏展开去掉类后
 * 元素失去 transition，margin 会瞬间归零而 transform 仍在过渡，造成底部「截断」感。
 * --chat-input-sink-shift：略大于原 1.125rem，以盖住底部提示行（mt-2 + text-xs）并略有余量。
 */
.chat-input-shell {
  --chat-input-sink-shift: 1.75rem;
  margin-top: 0;
  transition: margin-top var(--chat-input-trans-dur, 320ms) var(--chat-input-trans-ease, ease);
}

.chat-input-shell--sink {
  margin-top: calc(-1 * var(--chat-input-sink-shift));
}

.chat-input-morph-wrap {
  transition: transform var(--chat-input-trans-dur, 320ms) var(--chat-input-trans-ease, ease);
}

.chat-input-shell--sink .chat-input-morph-wrap {
  transform: translateY(var(--chat-input-sink-shift));
}

.chat-input-card-morph {
  transition:
    border-color 200ms ease,
    box-shadow 200ms ease,
    background-color 200ms ease;
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
  .chat-input-morph-wrap {
    transition: none !important;
    transform: none !important;
  }
  .chat-input-card-morph {
    transition: border-color 200ms ease, box-shadow 200ms ease, background-color 200ms ease !important;
  }
  .chat-input-footer-hint {
    transition: none !important;
  }
  .chat-input-placeholder-reveal {
    animation: none !important;
    clip-path: none !important;
  }
}

/* 与 TtsPlaybackFab：顶栏替代出现时隐藏可拖动栈（仍占位过渡） */
.assistant-fab-stack--hidden {
  visibility: hidden;
}

/* 与 TtsPlaybackFab .tts-top-bar-fade 同名，过渡时长一致 */
.tts-top-bar-fade-enter-active,
.tts-top-bar-fade-leave-active {
  transition: opacity 0.22s cubic-bezier(0.25, 1, 0.5, 1);
}

.tts-top-bar-fade-enter-from,
.tts-top-bar-fade-leave-to {
  opacity: 0;
}

/* 小于 TTS 顶栏 chip，气质对齐 TtsPlaybackFab .tts-top-bar-btn */
.agent-top-bar-btn {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  min-height: 1.75rem;
  padding: 0.3rem 0.6rem;
  border-radius: 0.75rem;
  border: 1px solid var(--color-border-subtle);
  background-color: var(--color-chrome-widget);
  background-image: none;
  color: var(--color-text-secondary);
  font-size: 0.6875rem;
  line-height: 1;
  cursor: pointer;
  overflow: hidden;
  backdrop-filter: blur(var(--blur-light));
  -webkit-backdrop-filter: blur(var(--blur-light));
  box-shadow: var(--shadow-glass-panel);
  transition:
    background-color 200ms cubic-bezier(0.25, 1, 0.5, 1),
    border-color 200ms cubic-bezier(0.25, 1, 0.5, 1),
    color 200ms cubic-bezier(0.25, 1, 0.5, 1),
    transform 180ms cubic-bezier(0.25, 1, 0.5, 1);
  animation: agentTopBarSlideIn 0.38s cubic-bezier(0.25, 1, 0.5, 1) backwards;
}

.agent-top-bar-btn--after-tts {
  animation-delay: 0.14s;
}

.agent-top-bar-btn__glow {
  position: absolute;
  inset: 0;
  opacity: 0.32;
  pointer-events: none;
  background-color: var(--color-brand-a20);
}

.agent-top-bar-btn__icon {
  width: 0.875rem;
  height: 0.875rem;
  flex-shrink: 0;
  color: var(--color-text);
  position: relative;
  z-index: 1;
}

.agent-top-bar-btn__label {
  position: relative;
  z-index: 1;
  font-weight: 400;
  letter-spacing: 0.04em;
  color: var(--color-text);
}

.agent-top-bar-btn:hover {
  background-color: var(--color-popover-surface);
  border-color: var(--color-border);
  color: var(--color-text);
}

.agent-top-bar-btn:active {
  transform: scale(0.97);
}

@keyframes agentTopBarSlideIn {
  from {
    opacity: 0;
    transform: translateY(-14px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@media (prefers-reduced-motion: reduce) {
  .agent-top-bar-btn {
    animation: none;
  }

  .tts-top-bar-fade-enter-active,
  .tts-top-bar-fade-leave-active {
    transition-duration: 0.01ms !important;
  }
}
</style>
