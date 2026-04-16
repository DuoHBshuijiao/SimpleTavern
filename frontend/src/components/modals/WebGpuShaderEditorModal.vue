<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { X } from 'lucide-vue-next'
import WgslMonospaceEditor from '../WgslMonospaceEditor.vue'
import type { WgslDiagnostic } from '../../utils/wgslCompilation'
import { errorLineNumbersFromDiagnostics } from '../../utils/wgslCompilation'

const props = defineProps<{
  show: boolean
  modelValue: string
  /** 用于在切换预设或重新打开弹窗时同步本地输入框 */
  presetId?: string | null
  presetName?: string
  disabled?: boolean
  adapterStatus: 'unknown' | 'available' | 'unavailable'
  hasRuntimeOverride?: boolean
  sourceDirty?: boolean
  /** WebGPU 编译诊断（结构化）；与 compileMessage 二选一或并存 */
  compileDiagnostics?: WgslDiagnostic[]
  /** 非 WGSL 编译类提示：适配器不可用、拉取失败等 */
  compileMessage?: string | null
  saveDisabled?: boolean
  compileDisabled?: boolean
  runDisabled?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:show', v: boolean): void
  (e: 'update:modelValue', v: string): void
  (e: 'update:presetName', v: string): void
  (e: 'compile'): void
  (e: 'save'): void
  (e: 'run'): void
}>()

const editorRef = ref<InstanceType<typeof WgslMonospaceEditor> | null>(null)

const diagnostics = computed(() => props.compileDiagnostics ?? [])

const errorLines = computed(() => errorLineNumbersFromDiagnostics(diagnostics.value))

const hasCompileIssue = computed(
  () => diagnostics.value.length > 0 || Boolean(props.compileMessage?.trim()),
)

function close() {
  emit('update:show', false)
}

function onInput(v: string) {
  emit('update:modelValue', v)
}

/** 与 props 解耦，避免父级 computed 在空名时回填默认名导致无法清空或 IME 被打断 */
const localPresetName = ref('')

watch(
  () => [props.show, props.presetId] as const,
  ([show]) => {
    if (show) localPresetName.value = props.presetName ?? ''
  },
  { immediate: true },
)

function onPresetNameInput(e: Event) {
  const v = (e.target as HTMLInputElement).value
  localPresetName.value = v
}

function commitPresetName() {
  emit('update:presetName', localPresetName.value)
}

const adapterLabel = computed(() =>
  props.adapterStatus === 'available'
    ? '可用'
    : props.adapterStatus === 'unavailable'
      ? '不可用'
      : '检测中',
)

function diagnosticTitle(d: WgslDiagnostic, index: number): string {
  if (d.line > 0) {
    const col = d.column > 0 ? `:${d.column}` : ''
    return `#${index + 1}  第 ${d.line} 行${col}`
  }
  return `#${index + 1}`
}

function scrollToDiagnostic(d: WgslDiagnostic) {
  if (d.line > 0) editorRef.value?.scrollToLogicalLine(d.line)
}

watch(
  [() => props.show, () => props.compileDiagnostics],
  () => {
    const diag = props.compileDiagnostics ?? []
    if (props.show && diag.length > 0) {
      const first = diag.find((x) => x.severity === 'error' && x.line > 0)
      if (first) {
        requestAnimationFrame(() => scrollToDiagnostic(first))
      }
    }
  },
  { deep: true },
)
</script>

<template>
  <Transition name="modal">
    <div v-if="show" class="modal">
      <div class="modal-backdrop backdrop-blur-[var(--blur-heavy)]" @click="close"></div>
      <div
        class="modal-content w-[80vw] max-w-[80vw] glass-panel theme-panel-bg backdrop-blur-[var(--blur-heavy)] backdrop-saturate-[1.8] border border-[var(--color-border)] flex flex-col min-h-0"
      >
        <div class="modal-header border-b border-[var(--color-border-subtle)] shrink-0">
          <h3 class="modal-title text-[var(--color-text)]">编辑 WGSL 着色器</h3>
          <button
            type="button"
            class="modal-close inline-flex min-h-11 min-w-11 items-center justify-center rounded-lg text-[var(--color-text-muted)] hover:text-[var(--color-text)] touch-manipulation"
            aria-label="关闭"
            @click="close"
          >
            <X class="h-5 w-5" />
          </button>
        </div>
        <div class="modal-body flex min-h-0 min-w-0 flex-1 flex-col gap-3 overflow-y-auto">
          <div class="flex w-full min-w-0 shrink-0 flex-col gap-1.5">
            <label
              class="block text-xs font-medium text-[var(--color-text-secondary)]"
              for="webgpu-shader-preset-name"
            >
              预设名称
            </label>
            <input
              id="webgpu-shader-preset-name"
              :value="localPresetName"
              type="text"
              class="input box-border w-full min-w-0"
              :disabled="disabled"
              placeholder="为此预设命名"
              @input="onPresetNameInput"
              @change="commitPresetName"
              @blur="commitPresetName"
              @keydown.stop
            />
          </div>
          <div class="flex shrink-0 flex-wrap items-center gap-2 text-xs text-[var(--color-text-muted)]">
            <span>适配器状态：{{ adapterLabel }}</span>
            <span v-if="hasRuntimeOverride">· 运行态覆盖已启用</span>
            <span v-if="sourceDirty">· 当前源码含未保存改动</span>
          </div>
          <div class="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
            <WgslMonospaceEditor
              ref="editorRef"
              :model-value="modelValue"
              :disabled="disabled"
              :error-lines="errorLines"
              placeholder="请选择或新建 WebGPU 预设后编辑 WGSL"
              @update:model-value="onInput"
            />
          </div>
          <div
            v-if="compileMessage"
            class="shrink-0 rounded-lg border border-[var(--color-error)]/35 bg-[var(--color-error-bg)] px-2.5 py-2 text-xs text-[var(--color-error-text)] whitespace-pre-wrap"
          >
            {{ compileMessage }}
          </div>
          <ul
            v-if="diagnostics.length > 0"
            class="shrink-0 list-none space-y-2 rounded-lg border border-[var(--color-error)]/35 bg-[var(--color-error-bg)] p-2.5 text-xs text-[var(--color-error-text)]"
            role="list"
          >
            <li
              v-for="(d, i) in diagnostics"
              :key="i"
              class="cursor-pointer rounded-md px-1.5 py-1 transition-colors hover:bg-[var(--color-surface-overlay)]"
              @click="scrollToDiagnostic(d)"
            >
              <div class="font-medium text-[var(--color-text-secondary)]">
                {{ diagnosticTitle(d, i) }}
              </div>
              <pre class="mt-1 max-h-40 overflow-y-auto whitespace-pre-wrap font-mono text-[11px] leading-relaxed text-[var(--color-error-text)]">{{ d.raw }}</pre>
            </li>
          </ul>
          <p
            v-if="!hasCompileIssue"
            class="shrink-0 text-xs text-[var(--color-text-muted)]"
          >
            Uniform 约定：`time`、`immersive`、`dpr`、`deltaTime`、`resolutionCss`、`resolutionPhysical`、`frameCounter`、`_padMouseAlign`、`mouseNorm`、`immersiveBlend`（向 immersive 平滑的 0–1，用于缓动）；主界面隐藏标签页时降频绘制。
          </p>
        </div>
        <div class="modal-footer shrink-0 flex flex-wrap justify-end gap-2">
          <button
            type="button"
            class="min-h-10 rounded-lg border border-[var(--color-border-subtle)] px-3 py-2 text-xs transition-colors hover:bg-surface-hover/30 disabled:opacity-50"
            :disabled="disabled || compileDisabled"
            @click="emit('compile')"
          >
            编译
          </button>
          <button
            type="button"
            class="min-h-10 rounded-lg border border-[var(--color-border-subtle)] px-3 py-2 text-xs transition-colors hover:bg-surface-hover/30 disabled:opacity-50"
            :disabled="disabled || saveDisabled"
            @click="emit('save')"
          >
            保存源码
          </button>
          <button
            type="button"
            class="min-h-10 rounded-lg bg-brand-a20 px-3 py-2 text-xs text-brand transition-colors hover:bg-brand-a30 disabled:opacity-50"
            :disabled="disabled || runDisabled"
            @click="emit('run')"
          >
            运行（仅本次）
          </button>
        </div>
      </div>
    </div>
  </Transition>
</template>
