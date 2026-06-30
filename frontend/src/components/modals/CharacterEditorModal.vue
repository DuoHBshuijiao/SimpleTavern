<script setup lang="ts">
import { X, Sparkles, Loader2, MoreHorizontal, GripVertical, Check, Plus, Globe } from 'lucide-vue-next'
import type { AssistantAttachment, CharacterCard, MvuMode } from '../../types/models'
import ModernAvatar from '../ModernAvatar.vue'
import ModernSelect from '../ModernSelect.vue'
import ThemedCheckbox from '../ThemedCheckbox.vue'
import { MvuCapabilityEditor, AssistantThread } from '../chat'
import { useDialogBehavior } from '../../composables/useDialogBehavior'
import { dialogAria } from '../../utils/uiPrimitives'
import { useCharacterEditor } from '../../composables/useCharacterEditor'
import type { ComponentPublicInstance } from 'vue'

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type ModelOption = any

const props = defineProps<{
  show: boolean
  isNewCharacter: boolean
  character: CharacterCard | null
  avatarUrl: string | null
  isNarrowPortrait: boolean
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  assistant: any
  assistantCurrentModel: string
  chatModelOptions: ModelOption[]
  isWorkspaceAssistantDragOver: boolean
  buildAssistantAttachmentUrl: (scope: 'chat' | 'workspace', attachment: AssistantAttachment) => string
  getAssistantAttachmentLabel: (attachment: AssistantAttachment) => string
  getAssistantAttachmentExt: (attachment: AssistantAttachment) => string
  bindWorkspaceMessagesListRef: (el: Element | ComponentPublicInstance | null) => void
  bindWorkspaceTextareaRef: (el: Element | ComponentPublicInstance | null) => void
  onWorkspacePaste: (event: ClipboardEvent) => void
  onWorkspaceDragEnter: (event: DragEvent) => void
  onWorkspaceDragLeave: (event: DragEvent) => void
  onWorkspaceDragOver: (event: DragEvent) => void
  onWorkspaceDrop: (event: DragEvent) => void | Promise<void>
  applyAssistantCard: (card: CharacterCard) => void
}>()

const emit = defineEmits<{
  'update:show': [value: boolean]
  cancel: []
  save: []
  export: []
  'open-avatar-cropper': []
  'open-assistant-settings': []
}>()

const editor = useCharacterEditor({
  editingCharacter: () => props.character,
  showEditor: () => props.show,
})

const {
  extraFirstMessageDraft,
  extraFirstMessageEntriesIndexed,
  hasAnyExtraFirstEntries,
  displayExtraEntryLabel,
  extraEntryIsEmpty,
  appendExtraFirstMessageCheck,
  appendExtraFirstMessagePlus,
  removeExtraFirstMessageAt,
  fillExtraFirstDraft,
  avatarObjectPositionByFocus,
  addCharacterEditorWbId,
  characterEditorWorldBookSelectOptions,
  characterEditorWbDraggingIdx,
  addCharacterEditorWorldBook,
  removeCharacterEditorWorldBook,
  moveCharacterEditorWorldBook,
  handleCharacterEditorWbDragStart,
  handleCharacterEditorWbDragOver,
  handleCharacterEditorWbDragEnd,
  loadCharacterEditorWorldbooks,
  characterEditorWorldBookName,
} = editor

defineExpose({ reloadWorldbooks: loadCharacterEditorWorldbooks })

const titleId = 'character-editor-title'
const dialogAttrs = dialogAria(titleId)
const { dialogRef } = useDialogBehavior(
  () => props.show,
  () => emit('cancel'),
)
void dialogRef
</script>

<template>
  <div v-if="show" class="modal">
    <div class="modal-backdrop" @click="emit('cancel')"></div>
    <div ref="dialogRef" v-bind="dialogAttrs" tabindex="-1" class="modal-content modal-surface chat-modal-width-1200-90">
      <div class="modal-header">
        <h3 :id="titleId" class="modal-title">{{ isNewCharacter ? '新建角色' : '编辑角色' }}</h3>
        <button type="button" class="modal-close" aria-label="关闭角色编辑弹窗" @click="emit('cancel')">
          <X class="w-5 h-5" />
        </button>
      </div>
      <div
        class="modal-body"
        :class="isNarrowPortrait ? 'max-h-[min(90dvh,800px)] min-h-0 overflow-x-hidden overflow-y-auto' : ''"
      >
        <div
          v-if="character"
          class="flex min-h-0 min-w-0"
          :class="isNarrowPortrait ? 'flex-col gap-4' : 'gap-6 h-[70vh]'"
        >
          <div
            class="min-h-0 min-w-0 pr-2 custom-scrollbar"
            :class="
              isNarrowPortrait
                ? 'shrink-0'
                : 'min-w-[min(50%,18rem)] flex-1 basis-0 overflow-y-auto'
            "
          >
            <div class="space-y-6">
              <div class="flex gap-6">
                <div class="flex flex-col items-center gap-3">
                  <ModernAvatar
                    :src="avatarUrl"
                    :size="120"
                    aspect="auto"
                    object-fit="cover"
                    :object-position="avatarObjectPositionByFocus(character.avatarFocusX, character.avatarFocusY)"
                    rounded="rounded-xl"
                    class="border-2 border-brand-a40 shadow-heavy bg-surface-overlay"
                  />
                  <button class="btn btn-sm btn-secondary" @click="emit('open-avatar-cropper')">更换头像</button>
                </div>
                <div class="flex-1 space-y-4">
                  <div class="form-group">
                    <label class="label">
                      <span>名称</span>
                      <span class="opacity-60 text-xs ml-2 text-brand">该项参与对话</span>
                    </label>
                    <input v-model="character.name" class="input" placeholder="角色名称" />
                  </div>
                  <div class="form-group">
                    <label class="label">简介</label>
                    <textarea v-model="character.description" class="input textarea h-20" placeholder="简短描述"></textarea>
                  </div>
                </div>
              </div>

              <div class="form-group">
                <label class="label">
                  <span>Personality（性格/外貌）</span>
                  <span class="opacity-60 text-xs ml-2 text-brand">该项参与对话</span>
                </label>
                <textarea v-model="character.personality" class="input textarea h-32" placeholder="详细设定..."></textarea>
              </div>

              <div class="form-group">
                <label class="label">
                  <span>Scenario（情景/世界观）</span>
                  <span class="opacity-60 text-xs ml-2 text-brand">该项参与对话</span>
                </label>
                <textarea v-model="character.scenario" class="input textarea h-24" placeholder="世界背景..."></textarea>
              </div>

              <div class="form-group">
                <label class="label">
                  <span>系统提示词</span>
                  <span class="opacity-60 text-xs ml-2 text-brand">该项参与对话</span>
                </label>
                <textarea v-model="character.systemPrompt" class="input textarea h-32" placeholder="回复格式要求..."></textarea>
              </div>

              <div class="form-group rounded-xl border border-[var(--color-border-subtle)] bg-surface-overlay/80 p-4 space-y-3">
                <label class="label">
                  <span>MVU 能力</span>
                </label>
                <label class="inline-flex items-center gap-2 text-sm text-[var(--color-text-secondary)] cursor-pointer select-none">
                  <ThemedCheckbox
                    :checked="character.mvuEnabled === true"
                    @update:checked="(v) => (character!.mvuEnabled = v)"
                  />
                  <span>启用 MVU 管线</span>
                </label>
                <MvuCapabilityEditor
                  :mvu-mode="character.mvuMode ?? 'regex'"
                  :mvu-directive="character.mvuDirective ?? ''"
                  :content-regex-rules="character.contentRegexRules || []"
                  :initial-state-tables="character.initialStateTables || []"
                  :allow-inherit="false"
                  tables-subtitle="新会话自动写入"
                  tables-empty-hint="暂无状态表格。新建表格后，新会话将自带初始状态栏。"
                  @update:mvu-mode="(v) => { character!.mvuMode = (v ?? 'regex') as MvuMode }"
                  @update:mvu-directive="(v) => { character!.mvuDirective = v }"
                  @update:content-regex-rules="(v) => { character!.contentRegexRules = v }"
                  @update:initial-state-tables="(v) => { character!.initialStateTables = v }"
                />
              </div>

              <div class="form-group">
                <label class="label">
                  <span>首句</span>
                  <span class="opacity-60 text-xs ml-2" v-pre>支持 {{user}} 占位符</span>
                  <span class="opacity-60 text-xs ml-2 text-brand">该项参与对话</span>
                </label>
                <textarea v-model="character.firstMessage" class="input textarea h-24" placeholder="开场白..."></textarea>
              </div>

              <div class="form-group">
                <label class="label">
                  <span>额外首句</span>
                  <span class="opacity-60 text-xs ml-2" v-pre>支持 {{user}} 占位符</span>
                  <span class="opacity-60 text-xs ml-2 text-brand">该项参与对话</span>
                </label>
                <div class="overflow-x-auto custom-scrollbar rounded-lg border border-[var(--color-border-subtle)] bg-surface-overlay/50 p-2">
                  <div class="flex w-full min-w-0 min-h-[6.5rem] flex-nowrap items-stretch gap-2">
                    <textarea
                      v-model="extraFirstMessageDraft"
                      class="input textarea h-24 max-w-full shrink-0"
                      :style="{
                        width: hasAnyExtraFirstEntries ? 'min(50%, 18rem)' : 'min(70%, 28rem)',
                      }"
                      placeholder="其他开场情景..."
                    />
                    <div class="flex shrink-0 flex-col justify-center gap-1.5">
                      <button
                        type="button"
                        class="inline-flex h-9 w-9 items-center justify-center rounded-md border border-[var(--color-border-subtle)] bg-surface-overlay text-[var(--color-text-secondary)] hover:bg-surface-muted transition-colors"
                        aria-label="追加为草稿（保留输入框）"
                        @click="appendExtraFirstMessageCheck()"
                      >
                        <Check class="w-[18px] h-[18px]" />
                      </button>
                      <button
                        type="button"
                        class="inline-flex h-9 w-9 items-center justify-center rounded-md border border-[var(--color-border-subtle)] bg-surface-overlay text-[var(--color-text-secondary)] hover:bg-surface-muted transition-colors"
                        aria-label="追加为已保存并清空输入"
                        @click="appendExtraFirstMessagePlus()"
                      >
                        <Plus class="w-[18px] h-[18px]" />
                      </button>
                    </div>
                    <div
                      v-if="extraFirstMessageEntriesIndexed.length"
                      class="flex shrink-0 items-stretch gap-2"
                    >
                      <div
                        v-for="entry in extraFirstMessageEntriesIndexed"
                        :key="entry.index"
                        class="flex shrink-0 items-start gap-1"
                      >
                        <button
                          type="button"
                          class="shrink-0 inline-flex flex-col items-start text-left px-3 py-2 text-xs border rounded-md hover:bg-surface-muted transition-colors w-[200px] min-h-[4.5rem] max-h-28 overflow-y-auto custom-scrollbar bg-surface-muted/80 text-[var(--color-text)]"
                          :class="
                            extraEntryIsEmpty(entry)
                              ? 'border-dashed border-[var(--color-border)] text-[var(--color-text-muted)]'
                              : 'border-[var(--color-border-subtle)]'
                          "
                          @click="fillExtraFirstDraft(entry.text)"
                        >
                          <span
                            v-if="entry.chip"
                            class="mb-1 shrink-0 rounded px-1 py-0.5 text-[10px] bg-brand-a10 text-brand border border-brand-a20"
                          >已保存</span>
                          <span
                            v-else
                            class="mb-1 shrink-0 rounded px-1 py-0.5 text-[10px] text-[var(--color-text-muted)] border border-[var(--color-border-subtle)]"
                          >草稿</span>
                          <span class="whitespace-pre-wrap break-words">{{ displayExtraEntryLabel(entry) }}</span>
                        </button>
                        <button
                          type="button"
                          class="shrink-0 inline-flex h-7 w-7 items-center justify-center rounded border border-[var(--color-border-subtle)] text-[var(--color-text-muted)] hover:bg-surface-muted hover:text-[var(--color-text)]"
                          aria-label="从列表移除此条"
                          @click.stop="removeExtraFirstMessageAt(entry.index)"
                        >
                          <X class="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
                <p class="text-xs text-[var(--color-text-muted)] mt-1.5 leading-relaxed">
                  对号：追加为草稿并保留输入；加号：追加为「已保存」并清空输入。仅「已保存」的额外首句会进入单聊开场变体；草稿仅本地编辑用。下方列出全部条目（含「（空）」），均可删除。保存角色时会去掉空文本；占位符替换后为空也不会写入变体。
                </p>
              </div>

              <div class="form-group">
                <label class="label">
                  <span>示例对话</span>
                  <span class="opacity-60 text-xs ml-2 text-brand">该项参与对话</span>
                </label>
                <textarea v-model="character.exampleDialogue" class="input textarea h-48" placeholder="示例对话..."></textarea>
              </div>

              <div class="form-group rounded-xl border border-[var(--color-border-subtle)] bg-surface-overlay/80 p-4">
                <label class="label">
                  <span>绑定世界书</span>
                  <span class="opacity-60 text-xs ml-2 text-brand">随角色保存；「角色+世界书」ZIP 导出用此顺序</span>
                </label>
                <p class="text-xs text-[var(--color-text-muted)] mb-3 leading-relaxed">
                  与「设置 → 当前会话」中的会话世界书顺序独立；保存后写入角色卡上的绑定列表，供含世界书 ZIP 等使用。
                </p>
                <div class="flex flex-wrap items-center gap-2 mb-3">
                  <ModernSelect
                    v-model="addCharacterEditorWbId"
                    :options="characterEditorWorldBookSelectOptions"
                    placeholder="选择世界书加入列表..."
                    class="flex-1 min-w-[200px]"
                  />
                  <button type="button" class="btn btn-sm btn-secondary shrink-0" @click="addCharacterEditorWorldBook()">加入</button>
                </div>
                <div class="space-y-1.5 max-h-[200px] overflow-y-auto custom-scrollbar pr-1">
                  <div
                    v-for="(wbId, idx) in (character.attachedWorldBookIds || [])"
                    :key="`${wbId}-${idx}`"
                    class="flex items-center justify-between gap-2 rounded-lg border border-[var(--color-border-subtle)] bg-surface-muted px-2 py-1.5 transition-all"
                    :class="characterEditorWbDraggingIdx === idx ? 'opacity-50 border-brand-a50' : ''"
                    draggable="true"
                    @dragstart="handleCharacterEditorWbDragStart(idx)"
                    @dragover="handleCharacterEditorWbDragOver($event, idx)"
                    @dragend="handleCharacterEditorWbDragEnd()"
                  >
                    <div class="flex min-w-0 flex-1 items-center gap-1.5">
                      <span class="shrink-0 cursor-grab text-[var(--color-text-muted)] active:cursor-grabbing" aria-hidden="true">
                        <GripVertical class="w-4 h-4" />
                      </span>
                      <span class="truncate text-xs text-[var(--color-text)]">{{ Number(idx) + 1 }}. {{ characterEditorWorldBookName(wbId) }}</span>
                    </div>
                    <div class="flex shrink-0 items-center gap-1">
                      <button type="button" class="btn btn-xs btn-secondary" @click.stop="moveCharacterEditorWorldBook(wbId, -1)">上移</button>
                      <button type="button" class="btn btn-xs btn-secondary" @click.stop="moveCharacterEditorWorldBook(wbId, 1)">下移</button>
                      <button type="button" class="btn btn-xs btn-secondary" @click.stop="removeCharacterEditorWorldBook(wbId)">移除</button>
                    </div>
                  </div>
                  <div v-if="!(character.attachedWorldBookIds || []).length" class="text-xs text-[var(--color-text-muted)] py-2 text-center border border-dashed border-[var(--color-border-subtle)] rounded-lg">
                    未绑定世界书
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div
            class="flex min-h-0 min-w-0 flex-col glass-panel rounded-2xl p-4 shadow-inner"
            :class="
              isNarrowPortrait
                ? 'min-h-[28rem] h-[min(36rem,72vh)] shrink-0 max-h-[min(576px,72vh)]'
                : 'max-w-[50%] flex-[0.66] basis-0'
            "
          >
            <div class="flex items-center justify-between mb-4 px-1">
              <span class="text-sm font-bold text-[var(--color-text-secondary)] uppercase tracking-widest flex items-center gap-2">
                <span class="w-2 h-2 rounded-full bg-brand animate-pulse"></span>
                聊天助手
              </span>
              <button class="text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors" @click="emit('open-assistant-settings')">
                <MoreHorizontal class="w-4 h-4" />
              </button>
            </div>
            <div
              :ref="bindWorkspaceMessagesListRef"
              class="min-h-0 min-w-0 flex-1 overflow-x-auto overflow-y-auto custom-scrollbar space-y-4 pr-2 mb-4"
            >
              <div v-if="assistant.workspaceAssistantMessages.value.length === 0" class="text-xs text-[var(--color-text-muted)] text-center py-12 flex flex-col items-center gap-3">
                <div class="w-12 h-12 rounded-full bg-surface-muted flex items-center justify-center text-xl">
                  <Sparkles class="w-6 h-6 text-[var(--color-warning)]" />
                </div>
                开始和助手对话以完善你的角色卡
              </div>
              <AssistantThread
                :messages="assistant.workspaceAssistantMessages.value"
                :is-generating="assistant.isWorkspaceAssistantGenerating.value"
                :attachment-scope="'workspace'"
                :streaming-content="assistant.workspaceStreamingContent.value"
                :streaming-reasoning="assistant.workspaceStreamingReasoning.value"
                :reasoning-stream-phase-active="assistant.workspaceReasoningStreamPhaseActive.value"
                :reasoning-elapsed-sec="assistant.workspaceReasoningElapsedSec.value"
                :show-message-actions="false"
              />
            </div>
            <div
              class="relative pt-4 border-t border-[var(--color-border-subtle)] transition-colors"
              @dragenter.prevent="onWorkspaceDragEnter"
              @dragover.prevent="onWorkspaceDragOver"
              @dragleave="onWorkspaceDragLeave"
              @drop.prevent="onWorkspaceDrop"
            >
              <div class="flex flex-wrap gap-2 mb-2 items-center">
                <button
                  type="button"
                  disabled
                  aria-label="记忆写入，仅聊天会话中可用"
                  class="text-xs px-2.5 py-1 rounded-lg border cursor-not-allowed opacity-50 border-[var(--color-border-subtle)] text-[var(--color-text-muted)]"
                >
                  记忆写入
                </button>
                <button
                  type="button"
                  class="text-xs px-2.5 py-1 rounded-lg border transition-colors"
                  :class="assistant.allowDestructiveToolsEnabled.value
                    ? 'bg-amber-500/15 border-amber-500/50 text-amber-200'
                    : 'border-[var(--color-border-subtle)] text-[var(--color-text-muted)]'"
                  @click="assistant.toggleAllowDestructiveTools"
                >
                  破坏性工具
                </button>
                <button
                  type="button"
                  class="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg border transition-colors"
                  :class="assistant.allowWebSearchEnabled.value
                    ? 'bg-brand/15 border-brand/50 text-brand-foreground'
                    : 'border-[var(--color-border-subtle)] text-[var(--color-text-muted)]'"
                  @click="assistant.toggleAllowWebSearch"
                >
                  <Globe class="h-3 w-3" />
                  网络搜索
                </button>
                <span class="text-[10px] text-[var(--color-text-muted)]">工作区不写长期记忆</span>
              </div>
              <div v-if="assistant.workspaceAssistantDraftAttachments.value.length" class="mb-3 flex flex-wrap gap-2">
                <template v-for="attachment in assistant.workspaceAssistantDraftAttachments.value" :key="attachment.id">
                  <div
                    v-if="attachment.kind === 'image'"
                    class="relative h-20 w-20 overflow-hidden rounded-lg border border-[var(--color-border)] bg-surface-muted"
                  >
                    <img :src="buildAssistantAttachmentUrl('workspace', attachment)" :alt="getAssistantAttachmentLabel(attachment)" class="h-full w-full object-cover" />
                    <button
                      type="button"
                      class="absolute right-1 top-1 flex h-5 w-5 items-center justify-center rounded-full border border-[var(--color-border-subtle)] bg-overlay-heavy text-[var(--color-text)]"
                      aria-label="移除图片附件"
                      @click="assistant.removeDraftAttachment('workspace', attachment.id)"
                    >
                      <X class="h-3 w-3" />
                    </button>
                  </div>
                  <button
                    v-else
                    type="button"
                    class="group relative flex max-w-[220px] items-start gap-2 rounded-xl border border-[var(--color-border)] bg-surface-muted px-3 py-2 text-left"
                    @click="assistant.removeDraftAttachment('workspace', attachment.id)"
                  >
                    <span class="rounded bg-surface-overlay px-1.5 py-0.5 text-[10px] font-semibold uppercase text-[var(--color-text-secondary)]">{{ getAssistantAttachmentExt(attachment) }}</span>
                    <span class="truncate text-xs text-[var(--color-text)]">{{ getAssistantAttachmentLabel(attachment) }}</span>
                    <X class="ml-auto mt-0.5 h-3 w-3 shrink-0 text-[var(--color-text-muted)] transition-colors group-hover:text-[var(--color-text)]" />
                  </button>
                </template>
              </div>
              <textarea
                :ref="bindWorkspaceTextareaRef"
                v-model="assistant.workspaceAssistantDraft.value"
                class="input textarea h-24"
                placeholder="输入建议或要求 (Ctrl + Enter)..."
                :disabled="assistant.isWorkspaceAssistantGenerating.value"
                @paste="onWorkspacePaste"
                @keydown.ctrl.enter="assistant.sendMessage('workspace', true, applyAssistantCard)"
              ></textarea>
              <div class="flex items-center justify-between mt-3 gap-3">
                <ModernSelect
                  :model-value="assistantCurrentModel"
                  :selected-preset-id="assistant.assistantSettings.value.presetId ?? null"
                  :options="chatModelOptions"
                  placement="top"
                  placeholder="模型..."
                  class="!w-[160px] !text-xs"
                  dropdown-width="410"
                  searchable
                  allow-create
                  @select="assistant.handleModelSelect"
                />
                <button
                  class="btn btn-primary relative px-6"
                  :disabled="(!assistant.workspaceAssistantDraft.value.trim() && !assistant.workspaceAssistantDraftAttachments.value.length) || assistant.isWorkspaceAssistantGenerating.value"
                  :aria-busy="assistant.isWorkspaceAssistantGenerating.value"
                  @click="assistant.sendMessage('workspace', true, applyAssistantCard)"
                >
                  <Loader2
                    v-if="assistant.isWorkspaceAssistantGenerating.value"
                    class="pointer-events-none absolute left-3 top-1/2 h-3 w-3 -translate-y-1/2 animate-spin"
                  />
                  发送
                </button>
              </div>
              <div
                v-show="isWorkspaceAssistantDragOver"
                class="pointer-events-none absolute inset-0 z-[21] rounded-xl bg-[var(--color-brand-a20)] backdrop-blur-[var(--glass-blur-soft)] ring-1 ring-inset ring-[var(--color-brand-a40)] transition-opacity duration-150"
                aria-hidden="true"
              />
            </div>
          </div>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" @click="emit('export')" :disabled="!character">导出角色 JSON</button>
        <button class="btn btn-secondary" @click="emit('cancel')">取消</button>
        <button class="btn btn-primary" @click="emit('save')">保存</button>
      </div>
    </div>
  </div>
</template>
