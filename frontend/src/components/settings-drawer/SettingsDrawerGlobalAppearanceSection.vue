<script setup lang="ts">
import { ref } from 'vue'
import ModernSelect from '../ModernSelect.vue'
import ThemedCheckbox from '../ThemedCheckbox.vue'
import SettingsDrawerGlobalAccordion from './SettingsDrawerGlobalAccordion.vue'
import { THEME_OPTIONS, type MvuMode, type Settings } from '../../types/models'
import type { SillyTavernImportPreview } from '../../composables/useSettingsImport'
import type { CSSProperties } from 'vue'

type WebgpuPreset = NonNullable<Settings['webgpuBackgroundPresets']>[number]

defineProps<{
  draft: Settings
  isNarrowPortrait: boolean
  pageBackgroundImageUrl: string | null | undefined
  pageBackgroundImageStyle: CSSProperties
  webgpuPresets: WebgpuPreset[]
  webgpuTargetFpsOptions: Array<{ label: string; value: string }>
  webgpuAvailability: 'unknown' | 'available' | 'unavailable'
  webgpuHasRuntimeOverride: boolean
  webgpuPresetSourceDirty: boolean
  webgpuPresetCompileDiagnosticsCount: number
  webgpuPresetCompileMessage: string | null
  webgpuPresetCreateBusy: boolean
  webgpuPresetDeleteBusy: boolean
  fontOptions: Array<{ label: string; value: string }>
  stPreview: SillyTavernImportPreview | null
  stPreviewLoading: boolean
  stDetectedMvu: boolean
  stMvuModeOptions: Array<{ label: string; value: string }>
  stPendingId: string
  stConfirming: boolean
  stImportConfirmLabel: string
  stExpiresAt: string
}>()

const open = defineModel<boolean>('open', { required: true })
const pageBackgroundOpacity = defineModel<number>('pageBackgroundOpacity', { required: true })
const pageBackgroundBlur = defineModel<number>('pageBackgroundBlur', { required: true })
const activeWebgpuPresetId = defineModel<string | null>('activeWebgpuPresetId', { required: true })
const webgpuTargetFps = defineModel<string>('webgpuTargetFps', { required: true })
const fontModel = defineModel<string>('fontModel', { required: true })
const messageFontSizeModel = defineModel<number | string>('messageFontSizeModel', { required: true })
const stEnableMvuCompatibility = defineModel<boolean>('stEnableMvuCompatibility', { required: true })
const stMvuMode = defineModel<MvuMode>('stMvuMode', { required: true })

const emit = defineEmits<{
  'clear-page-background': []
  'page-background-file': [event: Event]
  'create-webgpu-preset': []
  'open-webgpu-editor': [presetId: string]
  'run-webgpu-preset': []
  'delete-webgpu-preset': []
  'step-font-size': [delta: number]
  'font-file': [event: Event]
  backup: [mode: 'basic' | 'with_characters' | 'with_chats']
  'import-file': [event: Event]
  'st-import-file': [event: Event]
  'reset-st-preview': []
  'confirm-st-import': []
}>()

const pageBackgroundInputRef = ref<HTMLInputElement | null>(null)
const fontInputRef = ref<HTMLInputElement | null>(null)
const importInputRef = ref<HTMLInputElement | null>(null)
const stImportInputRef = ref<HTMLInputElement | null>(null)

function triggerPageBackgroundImport() {
  pageBackgroundInputRef.value?.click()
}

function triggerFontImport() {
  fontInputRef.value?.click()
}

function triggerImport() {
  importInputRef.value?.click()
}

function triggerStImport() {
  stImportInputRef.value?.click()
}
</script>

<template>
  <SettingsDrawerGlobalAccordion v-model:open="open" title="外观与数据" content-class="space-y-5">
    <div class="space-y-3 rounded-xl border border-[var(--color-border-subtle)] bg-[var(--color-settings-control-bg)] p-3.5">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div class="min-w-0 space-y-1">
          <div class="text-sm font-medium text-[var(--color-text-secondary)]">页面背景</div>
          <p class="text-xs leading-relaxed text-[var(--color-text-muted)]">
            图片只叠在主题底色之上；调低透明度时，底部纯色玻璃底会继续透出。
          </p>
        </div>
        <div class="flex flex-wrap gap-2">
          <button
            type="button"
            class="inline-flex min-h-10 items-center whitespace-nowrap rounded-lg bg-surface-muted px-4 py-2 text-sm text-[var(--color-text)] transition-colors hover:bg-surface-hover"
            @click="triggerPageBackgroundImport"
          >
            导入图片
          </button>
          <button
            v-if="draft.pageBackgroundImage"
            type="button"
            class="inline-flex min-h-10 items-center whitespace-nowrap rounded-lg border border-[var(--color-border-subtle)] bg-transparent px-4 py-2 text-sm text-[var(--color-text-secondary)] transition-colors hover:bg-surface-hover/30 hover:text-[var(--color-text)]"
            @click="emit('clear-page-background')"
          >
            清除
          </button>
        </div>
        <input
          ref="pageBackgroundInputRef"
          type="file"
          class="hidden"
          accept="image/*,.png,.jpg,.jpeg,.webp,.gif"
          @change="emit('page-background-file', $event)"
        />
      </div>

      <div
        v-if="pageBackgroundImageUrl"
        class="w-1/2 min-w-[12rem] max-w-[22rem] overflow-hidden rounded-xl border border-[var(--color-border-subtle)] bg-surface-muted/70"
      >
        <div class="h-32 overflow-hidden">
          <img
            :src="pageBackgroundImageUrl || ''"
            alt="页面背景预览"
            class="h-full w-full object-cover object-center"
            :style="pageBackgroundImageStyle"
          />
        </div>
      </div>
      <div
        v-else
        class="rounded-xl border border-dashed border-[var(--color-border-subtle)] bg-[var(--color-settings-control-bg)] px-3 py-4 text-xs leading-relaxed text-[var(--color-text-muted)]"
      >
        还未导入页面背景。聊天页将继续仅使用当前主题底色。
      </div>

      <div class="grid gap-3 md:grid-cols-2">
        <label class="space-y-2">
          <div class="flex items-center justify-between gap-2 text-xs text-[var(--color-text-secondary)]">
            <span>透明度</span>
            <span>{{ pageBackgroundOpacity }}%</span>
          </div>
          <input v-model="pageBackgroundOpacity" type="range" min="0" max="100" step="1" class="input-range" />
          <p class="text-xs text-[var(--color-text-muted)]">100% 为完整显示图片，降低后可透出主题底色。</p>
        </label>
        <label class="space-y-2">
          <div class="flex items-center justify-between gap-2 text-xs text-[var(--color-text-secondary)]">
            <span>模糊</span>
            <span>{{ pageBackgroundBlur }} px</span>
          </div>
          <input v-model="pageBackgroundBlur" type="range" min="0" max="64" step="1" class="input-range" />
          <p class="text-xs text-[var(--color-text-muted)]">仅作用于图片层，不会影响主题底色与界面内容。</p>
        </label>
      </div>
    </div>

    <div class="space-y-3 rounded-xl border border-[var(--color-border-subtle)] bg-[var(--color-settings-control-bg)] p-3.5">
      <div class="space-y-2">
        <div class="text-sm font-medium text-[var(--color-text-secondary)]">WebGPU 着色器背景</div>
        <p class="text-xs leading-relaxed text-[var(--color-text-muted)]">
          运行态可先编译并应用，不会自动写入后端；仅「保存设置」才持久化。
        </p>
        <label class="block text-sm font-medium text-[var(--color-text-secondary)]">启用着色器背景</label>
        <button
          type="button"
          class="group flex min-h-11 w-full cursor-pointer items-center gap-3 py-1 text-left"
          @click="draft.webgpuBackgroundEnabled = !draft.webgpuBackgroundEnabled"
        >
          <div
            class="relative h-6 w-11 shrink-0 rounded-full transition-colors duration-200 ease-out"
            :class="draft.webgpuBackgroundEnabled ? 'bg-brand' : 'bg-[var(--color-track)]'"
          >
            <div
              class="absolute left-1 top-1 h-4 w-4 rounded-full bg-[var(--color-on-brand)]"
              :style="{
                transform: draft.webgpuBackgroundEnabled ? 'translateX(1.25rem)' : 'translateX(0)',
                transition: 'transform 200ms ease-out',
              }"
            />
          </div>
          <span class="text-xs text-[var(--color-text-secondary)]">
            {{ draft.webgpuBackgroundEnabled ? '已启用' : '已关闭' }}
          </span>
        </button>
      </div>

      <div class="flex flex-wrap gap-2">
        <button
          type="button"
          class="min-h-9 rounded-lg bg-surface-muted px-3 py-1.5 text-xs transition-colors hover:bg-surface-hover disabled:opacity-50"
          :disabled="webgpuPresetCreateBusy"
          @click="emit('create-webgpu-preset')"
        >
          新建预设
        </button>
      </div>

      <div class="space-y-2">
        <div class="flex items-center justify-between gap-3">
          <span class="text-xs text-[var(--color-text-secondary)]">活动预设</span>
          <div class="flex shrink-0 items-center gap-1.5">
            <span class="whitespace-nowrap text-2xs text-[var(--color-text-muted)]">渲染性能</span>
            <ModernSelect
              v-model="webgpuTargetFps"
              :options="webgpuTargetFpsOptions"
              placement="top"
              class="w-[96px] min-w-0"
            />
          </div>
        </div>
        <div class="flex flex-wrap items-center gap-x-2 gap-y-1 text-2xs leading-snug text-[var(--color-text-muted)]">
          <span>适配器：{{ webgpuAvailability === 'available' ? '可用' : webgpuAvailability === 'unavailable' ? '不可用' : '检测中' }}</span>
          <span v-if="webgpuHasRuntimeOverride">· 运行态覆盖</span>
          <span v-if="webgpuPresetSourceDirty">· 未保存</span>
        </div>
        <p
          v-if="webgpuPresetCompileDiagnosticsCount > 0 || webgpuPresetCompileMessage"
          class="text-xs text-[var(--color-error-text)]"
        >
          编译失败，请使用对应预设行的「编辑」查看详情。
        </p>
        <div class="space-y-2 rounded-lg border border-[var(--color-border-subtle)] bg-[var(--color-settings-control-bg)] p-2">
          <template v-for="item in webgpuPresets" :key="item.id">
            <div
              class="flex min-h-9 w-full flex-wrap items-center gap-1.5 rounded-md px-1 py-0.5 text-xs outline-none transition-colors focus-visible:ring-2 focus-visible:ring-brand-a40"
              :class="
                item.id === activeWebgpuPresetId
                  ? 'cursor-pointer bg-brand-a20 text-brand ring-1 ring-brand-a30'
                  : 'cursor-pointer hover:bg-surface-hover/40'
              "
              tabindex="0"
              @click="activeWebgpuPresetId = item.id"
              @keydown.enter.prevent="activeWebgpuPresetId = item.id"
              @keydown.space.prevent="activeWebgpuPresetId = item.id"
            >
              <div class="flex min-h-9 min-w-0 flex-1 basis-[min(100%,10rem)] items-center px-2 py-1">
                <span class="truncate">{{ item.name }}</span>
              </div>
              <div class="flex flex-wrap items-center gap-1.5" @click.stop>
                <button
                  type="button"
                  class="min-h-8 shrink-0 rounded-md border border-[var(--color-border-subtle)] px-2 py-1 text-2xs text-[var(--color-text-secondary)] transition-colors hover:bg-surface-hover/40 hover:text-[var(--color-text)]"
                  :class="item.id === activeWebgpuPresetId ? 'border-[var(--color-border-subtle)]/80' : ''"
                  @click="emit('open-webgpu-editor', item.id)"
                >
                  编辑
                </button>
                <template v-if="item.id === activeWebgpuPresetId">
                  <button
                    type="button"
                    class="min-h-8 shrink-0 rounded-md border border-[var(--color-border-subtle)] px-2 py-1 text-2xs transition-colors hover:bg-surface-hover/30"
                    @click="emit('run-webgpu-preset')"
                  >
                    运行
                  </button>
                  <button
                    type="button"
                    class="min-h-8 shrink-0 rounded-md border border-[color-mix(in_srgb,var(--color-error)_40%,transparent)] px-2 py-1 text-2xs text-[var(--color-error-text)] transition-colors hover:bg-[var(--color-danger-hover)] disabled:opacity-50"
                    :disabled="webgpuPresetDeleteBusy"
                    @click="emit('delete-webgpu-preset')"
                  >
                    删除
                  </button>
                </template>
              </div>
            </div>
          </template>
          <div v-if="webgpuPresets.length === 0" class="px-2 py-2 text-xs text-[var(--color-text-muted)]">
            暂无预设
          </div>
        </div>
      </div>
    </div>

    <div class="space-y-1.5">
      <label class="block text-sm font-medium text-[var(--color-text-secondary)]">界面色系</label>
      <ModernSelect
        v-model="draft.themeId"
        :options="[...THEME_OPTIONS]"
        placeholder="选择色系..."
        class="w-full"
      />
      <p class="text-xs text-[var(--color-text-muted)]">暗色玻璃底，仅强调色随主题变化；未设置时默认为雾玫瑰。</p>
    </div>

    <div class="space-y-3">
      <div class="text-sm font-medium text-[var(--color-text-secondary)]">字体</div>
      <div class="gap-2" :class="isNarrowPortrait ? 'flex flex-col' : 'flex flex-wrap items-center'">
        <div class="relative min-w-0 group" :class="isNarrowPortrait ? 'w-full' : 'max-w-[172px] flex-1'">
          <ModernSelect
            v-model="fontModel"
            :options="fontOptions"
            placement="top"
            searchable
            placeholder="选择字体..."
            class="w-full min-w-0"
          />
        </div>
        <div class="flex flex-wrap items-center gap-2" :class="isNarrowPortrait ? 'w-full' : ''">
          <div class="flex h-10 items-center gap-0.5 rounded-lg border border-[var(--color-border)] bg-surface-muted px-1 py-0.5">
            <button
              type="button"
              class="flex min-h-9 min-w-9 items-center justify-center rounded-md p-2 text-[var(--color-text-muted)] transition-colors hover:bg-surface-hover hover:text-[var(--color-text)]"
              aria-label="减小字号"
              @click="emit('step-font-size', -1)"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"/></svg>
            </button>
            <input
              v-model.number="messageFontSizeModel"
              type="number"
              min="8"
              max="72"
              placeholder=""
              class="w-10 border-0 bg-transparent text-center text-sm text-[var(--color-text)] [appearance:textfield] focus:outline-none focus:ring-0 [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
            />
            <button
              type="button"
              class="flex min-h-9 min-w-9 items-center justify-center rounded-md p-2 text-[var(--color-text-muted)] transition-colors hover:bg-surface-hover hover:text-[var(--color-text)]"
              aria-label="增大字号"
              @click="emit('step-font-size', 1)"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            </button>
          </div>
          <button
            type="button"
            class="inline-flex min-h-10 items-center whitespace-nowrap rounded-lg bg-surface-muted px-4 py-2 text-sm text-[var(--color-text)] transition-colors hover:bg-surface-hover"
            @click="triggerFontImport"
          >
            导入字体
          </button>
          <input
            ref="fontInputRef"
            type="file"
            class="hidden"
            accept=".ttf,.otf,.woff,.woff2"
            @change="emit('font-file', $event)"
          />
        </div>
      </div>
    </div>

    <div class="space-y-3">
      <div class="text-sm font-medium text-[var(--color-text-secondary)]">数据备份与导入</div>
      <div class="flex flex-col gap-2">
        <div class="grid grid-cols-2 gap-2">
          <button
            type="button"
            class="min-h-10 min-w-0 rounded-lg bg-surface-muted px-3 py-2 text-center text-sm leading-tight text-[var(--color-text)] transition-colors hover:bg-surface-hover"
            @click="emit('backup', 'basic')"
          >
            基本设置
          </button>
          <button
            type="button"
            class="min-h-10 min-w-0 rounded-lg bg-surface-muted px-3 py-2 text-center text-sm leading-tight text-[var(--color-text)] transition-colors hover:bg-surface-hover"
            @click="emit('backup', 'with_characters')"
          >
            包含角色卡
          </button>
        </div>
        <div class="grid grid-cols-2 gap-2">
          <button
            type="button"
            class="min-h-10 min-w-0 rounded-lg bg-surface-muted px-3 py-2 text-center text-sm leading-tight text-[var(--color-text)] transition-colors hover:bg-surface-hover"
            @click="emit('backup', 'with_chats')"
          >
            包含全部聊天记录
          </button>
          <button
            type="button"
            class="min-h-10 min-w-0 rounded-lg bg-surface-muted px-3 py-2 text-center text-sm leading-tight text-[var(--color-text)] transition-colors hover:bg-surface-hover"
            :disabled="stPreviewLoading"
            @click="triggerImport"
          >
            {{ stPreviewLoading ? '读取预览中…' : '导入数据' }}
          </button>
        </div>
        <button
          type="button"
          class="min-h-10 w-full rounded-lg border border-[var(--color-border-subtle)] bg-[var(--color-surface-overlay)] px-3 py-2 text-center text-sm leading-tight text-[var(--color-text-secondary)] transition-colors hover:bg-surface-hover"
          :disabled="stPreviewLoading"
          @click="triggerStImport"
        >
          {{ stPreviewLoading ? '读取预览中…' : '仅选择 SillyTavern 角色卡（PNG / JSON）' }}
        </button>
        <input
          ref="importInputRef"
          type="file"
          class="hidden"
          accept=".txt,.json,.jsonl,.zip,.png"
          @change="emit('import-file', $event)"
        />
        <input ref="stImportInputRef" type="file" class="hidden" accept=".png,.json" @change="emit('st-import-file', $event)" />
        <div
          v-if="stPreview"
          class="rounded-lg border border-[var(--color-border-subtle)] bg-[var(--color-surface-overlay)] p-3 text-xs text-[var(--color-text-muted)]"
        >
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div class="text-[var(--color-text-secondary)]">SillyTavern 预览</div>
            <button
              type="button"
              class="min-h-8 rounded-md bg-surface-muted px-2 py-1 text-[var(--color-text)] hover:bg-surface-hover"
              @click="emit('reset-st-preview')"
            >
              清除
            </button>
          </div>
          <div class="mt-2">
            角色名：<span class="text-[var(--color-text)]">{{ stPreview.characterName || '未知' }}</span>
          </div>
          <div class="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
            <div>世界书：<span class="text-[var(--color-text)]">{{ stPreview.worldBookName || '未检测到' }}</span></div>
            <div>世界书条目：<span class="text-[var(--color-text)]">{{ stPreview.worldBookEntryCount }}</span></div>
            <div>tavern_helper：<span class="text-[var(--color-text)]">{{ stPreview.mvu.hasTavernHelper ? '已检测到' : '未检测到' }}</span></div>
            <div>regex_scripts：<span class="text-[var(--color-text)]">{{ stPreview.mvu.regexScriptCount }}</span></div>
          </div>
          <label class="mt-3 flex items-center gap-2 text-[var(--color-text-muted)]">
            <ThemedCheckbox :checked="stEnableMvuCompatibility" @update:checked="stEnableMvuCompatibility = $event" />
            启用 MVU 兼容
            <span v-if="stDetectedMvu" class="text-[var(--color-text-secondary)]">已检测到候选结构</span>
          </label>
          <p class="text-[var(--color-text-muted)]">
            指令模式会把完整 ST 卡上下文交给 MVU Agent，生成角色卡 MVU 指令与初始状态栏后再完成导入。
          </p>
          <div class="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
            <div>
              <div class="mb-1 text-[var(--color-text-muted)]">MVU 模式</div>
              <ModernSelect
                v-model="stMvuMode"
                :options="stMvuModeOptions"
                placeholder="选择 MVU 模式"
              />
            </div>
            <button
              type="button"
              class="btn btn-sm btn-primary min-h-10 w-full sm:w-auto"
              :disabled="!stPendingId || stConfirming"
              @click="emit('confirm-st-import')"
            >
              {{ stImportConfirmLabel }}
            </button>
          </div>
          <div v-if="stExpiresAt" class="mt-2 text-[var(--color-text-muted)]">预览暂存至：{{ stExpiresAt }}</div>
        </div>
      </div>
      <div class="text-xs text-[var(--color-text-muted)]">
        PNG 或 SillyTavern 形状 JSON 会先显示预览并可勾选 MVU；普通备份 JSON 仍走一键导入。
      </div>
      <div class="text-xs text-[var(--color-text-muted)]">
        备份会导出全部系统设置（含用户 Persona 头像）；“包含角色卡/包含全部聊天记录”同时包含世界书数据。
      </div>
    </div>
  </SettingsDrawerGlobalAccordion>
</template>
