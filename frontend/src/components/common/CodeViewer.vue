<script setup lang="ts">
/**
 * CodeViewer - 通用只读代码查看器
 *
 * 从 WgslMonospaceEditor 抽出视觉骨架（等宽 + 行号 + 主题变量），叠加：
 *  - JSON 语法着色（key / string / number / bool / null）
 *  - 基于缩进层级的自动折叠（默认 foldLevel=2，再深的层级初始折叠）
 *  - 点击行号左侧 Chevron 展开 / 折叠
 *  - 行高对齐：沿用 WgslMonospaceEditor 的离屏采样测量真实像素行高，两列使用
 *    相同 paddingTop/Bottom（px）、相同 items-start 顶对齐、每行显式 height +
 *    lineHeight，避免 line-height 小数与 min-height 冲突导致"行越多越偏"
 *
 * 不引入 Monaco / Prism / Shiki 等重型依赖，保持轻量。
 *
 * Props:
 *  - modelValue: 要展示的文本
 *  - language: 'json' | 'plain'
 *  - foldLevel: JSON 模式下，层级 > foldLevel 的块初始折叠；默认 2
 *  - showLineNumbers: 是否展示行号列，默认 true
 *  - minHeightClass: 滚动区额外类名
 *  - maxHeightClass: 滚动区最大高度类名，例如 max-h-[60vh]
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ChevronDown, ChevronRight } from 'lucide-vue-next'

type Language = 'json' | 'plain'

const props = withDefaults(
  defineProps<{
    modelValue: string
    language?: Language
    foldLevel?: number
    showLineNumbers?: boolean
    minHeightClass?: string
    maxHeightClass?: string
  }>(),
  {
    language: 'plain',
    foldLevel: 2,
    showLineNumbers: true,
    minHeightClass: '',
    maxHeightClass: 'max-h-[60vh]',
  },
)

// 两列共用的垂直内边距（像素），必须与模板上的 style 一致
const VERTICAL_PAD_PX = 8

type Token =
  | { kind: 'plain'; text: string }
  | { kind: 'key'; text: string }
  | { kind: 'string'; text: string }
  | { kind: 'number'; text: string }
  | { kind: 'bool'; text: string }
  | { kind: 'null'; text: string }
  | { kind: 'punct'; text: string }

type LineInfo = {
  indent: number
  tokens: Token[]
  raw: string
  /** 若此行以 `{` / `[` 开头括号（在该行末尾或行尾结构），记录其闭合行号（>= 本行）；否则 -1 */
  blockEndLine: number
}

const FOLD_MIN_SPAN = 1

function tokenizeJsonLine(line: string): Token[] {
  const out: Token[] = []
  let i = 0
  const len = line.length
  let sawColonThisRun = false

  const at = (idx: number): string => (idx >= 0 && idx < len ? line.charAt(idx) : '')
  const isDigit = (c: string) => c >= '0' && c <= '9'

  while (i < len) {
    const c = at(i)
    if (c === '"') {
      let j = i + 1
      let closed = false
      while (j < len) {
        const cc = at(j)
        if (cc === '\\' && j + 1 < len) {
          j += 2
          continue
        }
        if (cc === '"') {
          closed = true
          j++
          break
        }
        j++
      }
      if (!closed) j = len
      const raw = line.slice(i, j)
      let k = j
      while (k < len && (at(k) === ' ' || at(k) === '\t')) k++
      if (k < len && at(k) === ':' && !sawColonThisRun) {
        out.push({ kind: 'key', text: raw })
      } else {
        out.push({ kind: 'string', text: raw })
      }
      i = j
      continue
    }
    if (c === '{' || c === '}' || c === '[' || c === ']' || c === ',') {
      out.push({ kind: 'punct', text: c })
      i++
      continue
    }
    if (c === ':') {
      sawColonThisRun = true
      out.push({ kind: 'punct', text: c })
      i++
      continue
    }
    if (isDigit(c) || (c === '-' && i + 1 < len && isDigit(at(i + 1)))) {
      let j = i + 1
      while (j < len && /[0-9.eE+\-]/.test(at(j))) j++
      out.push({ kind: 'number', text: line.slice(i, j) })
      i = j
      continue
    }
    if (line.startsWith('true', i) || line.startsWith('false', i)) {
      const len2 = line.startsWith('true', i) ? 4 : 5
      out.push({ kind: 'bool', text: line.slice(i, i + len2) })
      i += len2
      continue
    }
    if (line.startsWith('null', i)) {
      out.push({ kind: 'null', text: 'null' })
      i += 4
      continue
    }
    const j = i + 1
    out.push({ kind: 'plain', text: line.slice(i, j) })
    i = j
  }
  return out
}

/** 计算每行缩进（空格数）；tab 视为 2。 */
function computeIndent(line: string): number {
  let count = 0
  for (let i = 0; i < line.length; i++) {
    const c = line.charAt(i)
    if (c === ' ') count++
    else if (c === '\t') count += 2
    else break
  }
  return count
}

/** 扫描 JSON 文本，为每行计算 block end line（用于折叠）。 */
function buildLineInfos(text: string, language: Language): LineInfo[] {
  const rawLines = text.split('\n')
  const infos: LineInfo[] = rawLines.map((raw) => ({
    indent: computeIndent(raw),
    tokens: language === 'json' ? tokenizeJsonLine(raw) : [{ kind: 'plain', text: raw }],
    raw,
    blockEndLine: -1,
  }))

  if (language !== 'json') return infos

  const stack: number[] = []
  for (let i = 0; i < infos.length; i++) {
    const raw = infos[i]?.raw ?? ''
    let inString = false
    let escape = false
    for (let k = 0; k < raw.length; k++) {
      const c = raw.charAt(k)
      if (escape) {
        escape = false
        continue
      }
      if (c === '\\' && inString) {
        escape = true
        continue
      }
      if (c === '"') {
        inString = !inString
        continue
      }
      if (inString) continue
      if (c === '{' || c === '[') {
        stack.push(i)
      } else if (c === '}' || c === ']') {
        const start = stack.pop()
        if (start !== undefined && start !== i && i - start >= FOLD_MIN_SPAN) {
          const target = infos[start]
          if (target) target.blockEndLine = i
        }
      }
    }
  }
  return infos
}

/** 根据括号层级（栈深度）推断每行所处层级，用于初始折叠判断。 */
function computeLineDepths(infos: LineInfo[]): number[] {
  const depths = new Array<number>(infos.length).fill(0)
  let depth = 0
  for (let i = 0; i < infos.length; i++) {
    const raw = infos[i]?.raw ?? ''
    const lineStartDepth = depth
    let inString = false
    let escape = false
    let lineClosesBeforeAnyOpen = 0
    let sawOpen = false
    for (let k = 0; k < raw.length; k++) {
      const c = raw.charAt(k)
      if (escape) {
        escape = false
        continue
      }
      if (c === '\\' && inString) {
        escape = true
        continue
      }
      if (c === '"') {
        inString = !inString
        continue
      }
      if (inString) continue
      if (c === '{' || c === '[') {
        sawOpen = true
        depth++
      } else if (c === '}' || c === ']') {
        if (!sawOpen) lineClosesBeforeAnyOpen++
        depth = Math.max(0, depth - 1)
      }
    }
    // 以"进入本行时"的栈深度作为行层级，使第一个 `{` 显示在层级 0、其花括号内的 key 显示为层级 1
    const d = lineStartDepth - lineClosesBeforeAnyOpen
    depths[i] = d < 0 ? 0 : d
  }
  return depths
}

const infos = computed<LineInfo[]>(() => buildLineInfos(props.modelValue ?? '', props.language))

const foldedStarts = ref<Set<number>>(new Set())

/**
 * 行高测量（借鉴 WgslMonospaceEditor）：
 * 不采用 line-height: 1.6 + min-height: 1.4rem 的组合（两者会在浏览器四舍五入
 * 下相互冲突，行数越多错位越大），而是用离屏采样一行"M"在与内容列相同
 * 字体 / line-height 下的真实像素高度，把这个 px 值作为两列每行的显式
 * height + lineHeight，使行号与内容 row-by-row 严格对齐。
 */
const contentRootRef = ref<HTMLElement | null>(null)
/** 与滚动容器 scrollHeight 同步，供行号区全高背景（避免 sticky / inset-0 与 flex 组合下仅覆盖视口） */
const scrollAreaRef = ref<HTMLElement | null>(null)
const gutterBackdropHeightPx = ref(0)
const lineHeightPx = ref(18)

function measureLineHeightPx(): number {
  const host = contentRootRef.value
  if (!host) return 18
  const cs = getComputedStyle(host)
  const d = document.createElement('div')
  d.style.cssText =
    'position:absolute;visibility:hidden;left:-99999px;top:0;white-space:pre;margin:0;padding:0;border:none;box-sizing:border-box;'
  d.style.fontFamily = cs.fontFamily
  d.style.fontSize = cs.fontSize
  d.style.fontWeight = cs.fontWeight
  d.style.fontStyle = cs.fontStyle
  d.style.lineHeight = cs.lineHeight
  d.style.letterSpacing = cs.letterSpacing
  d.textContent = 'M'
  document.body.appendChild(d)
  const h = d.offsetHeight
  document.body.removeChild(d)
  return Math.max(1, Math.ceil(h))
}

function syncGutterBackdropHeight() {
  if (!props.showLineNumbers) return
  void nextTick(() => {
    requestAnimationFrame(() => {
      const el = scrollAreaRef.value
      const sh = el?.scrollHeight ?? 0
      /** 与行号列理论高度取较大值，避免同一帧 layout 未提交时 scrollHeight 暂短一截 */
      const pad = VERTICAL_PAD_PX * 2
      const rowsH = displayRows.value.length * lineHeightPx.value
      gutterBackdropHeightPx.value = Math.max(sh, pad + rowsH)
    })
  })
}

function resyncLineHeight() {
  void nextTick(() => {
    const h = measureLineHeightPx()
    if (h > 0) lineHeightPx.value = h
    syncGutterBackdropHeight()
  })
}

const rowStyle = computed(() => ({
  height: `${lineHeightPx.value}px`,
  minHeight: `${lineHeightPx.value}px`,
  lineHeight: `${lineHeightPx.value}px`,
  boxSizing: 'border-box' as const,
}))

const verticalPadStyle = computed(() => ({
  paddingTop: `${VERTICAL_PAD_PX}px`,
  paddingBottom: `${VERTICAL_PAD_PX}px`,
}))

let ro: ResizeObserver | null = null

onMounted(() => {
  resyncLineHeight()
  syncGutterBackdropHeight()
  if (typeof ResizeObserver !== 'undefined') {
    ro = new ResizeObserver(() => resyncLineHeight())
    if (contentRootRef.value) ro.observe(contentRootRef.value)
  }
  window.addEventListener('resize', resyncLineHeight)
})

onBeforeUnmount(() => {
  if (ro) ro.disconnect()
  ro = null
  window.removeEventListener('resize', resyncLineHeight)
})

watch(
  () => props.modelValue,
  () => resyncLineHeight(),
  { flush: 'post' },
)

watch(
  () => props.showLineNumbers,
  () => syncGutterBackdropHeight(),
  { flush: 'post' },
)

watch(
  () => [props.modelValue, props.language, props.foldLevel] as const,
  () => {
    const next = new Set<number>()
    if (props.language === 'json') {
      const is = buildLineInfos(props.modelValue ?? '', 'json')
      const ds = computeLineDepths(is)
      for (let i = 0; i < is.length; i++) {
        const info = is[i]
        if (!info) continue
        if (info.blockEndLine <= i) continue
        if ((ds[i] ?? 0) >= (props.foldLevel ?? 2)) {
          next.add(i)
        }
      }
    }
    foldedStarts.value = next
  },
  { immediate: true },
)

type DisplayRow = {
  kind: 'line' | 'placeholder'
  lineIndex: number
  /** placeholder 模式下折叠了多少行 */
  foldedLines?: number
  /** placeholder 模式下对应的起始行 */
  startLine?: number
}

const displayRows = computed<DisplayRow[]>(() => {
  const rows: DisplayRow[] = []
  const lines = infos.value
  let i = 0
  while (i < lines.length) {
    rows.push({ kind: 'line', lineIndex: i })
    if (foldedStarts.value.has(i)) {
      const line = lines[i]
      const end = line ? line.blockEndLine : -1
      if (end > i) {
        rows.push({
          kind: 'placeholder',
          lineIndex: i,
          foldedLines: end - i - 1,
          startLine: i,
        })
        i = end
        continue
      }
    }
    i++
  }
  return rows
})

watch(
  displayRows,
  () => syncGutterBackdropHeight(),
  { flush: 'post' },
)

function toggleFold(startLine: number) {
  const set = new Set(foldedStarts.value)
  if (set.has(startLine)) set.delete(startLine)
  else set.add(startLine)
  foldedStarts.value = set
}

function canFold(lineIndex: number): boolean {
  if (props.language !== 'json') return false
  const info = infos.value[lineIndex]
  return !!info && info.blockEndLine > lineIndex
}

function lineTokens(lineIndex: number): Token[] {
  return infos.value[lineIndex]?.tokens ?? []
}

function tokenClass(kind: Token['kind']): string {
  switch (kind) {
    case 'key':
      return 'text-[var(--color-brand)]'
    case 'string':
      return 'text-emerald-300'
    case 'number':
      return 'text-amber-300'
    case 'bool':
      return 'text-sky-300'
    case 'null':
      return 'text-zinc-400'
    case 'punct':
      return 'text-[var(--color-text-muted)]'
    default:
      return 'text-[var(--color-text-primary)]'
  }
}

function lineNumberText(n: number): string {
  return String(n + 1)
}
</script>

<template>
  <div
    class="code-viewer flex min-h-0 w-full min-w-0 flex-1 flex-col overflow-hidden rounded-lg border border-[var(--color-border-default)] bg-[var(--color-dark-surface)]"
  >
    <div
      ref="scrollAreaRef"
      class="relative flex min-h-0 w-full min-w-0 flex-1 flex-row items-start overflow-auto"
      :class="[minHeightClass, maxHeightClass]"
    >
      <!-- 全高行号背景：高度取滚动容器 scrollHeight，避免 sticky / absolute inset 仅覆盖初始视口 -->
      <div
        v-if="showLineNumbers"
        class="pointer-events-none absolute left-0 top-0 z-[1] w-[3.5rem] border-r border-[var(--color-border-subtle)] bg-[var(--color-surface-muted)]"
        :style="{ height: `${gutterBackdropHeightPx}px` }"
        aria-hidden="true"
      />
      <!-- 行号 + 折叠指示列：与内容列共享 paddingTop/Bottom 像素、font 堆栈、每行显式 height+lineHeight -->
      <div
        v-if="showLineNumbers"
        class="sticky left-0 z-[2] flex shrink-0 select-none flex-col bg-transparent font-mono text-[11px] text-[var(--color-text-muted)]"
        :style="{ width: '3.5rem', ...verticalPadStyle }"
      >
        <div
          v-for="(row, idx) in displayRows"
          :key="'ln-' + idx + '-' + row.lineIndex"
          class="tabular-nums flex items-start justify-end gap-1 px-1.5"
          :style="rowStyle"
        >
          <button
            v-if="row.kind === 'line' && canFold(row.lineIndex)"
            type="button"
            class="inline-flex h-3 w-3 shrink-0 items-center justify-center rounded text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]"
            :style="{ marginTop: `${Math.max(0, Math.floor((lineHeightPx - 12) / 2))}px` }"
            :aria-label="foldedStarts.has(row.lineIndex) ? '展开' : '折叠'"
            @click="toggleFold(row.lineIndex)"
          >
            <ChevronDown v-if="!foldedStarts.has(row.lineIndex)" class="h-3 w-3" />
            <ChevronRight v-else class="h-3 w-3" />
          </button>
          <span v-else class="inline-block h-3 w-3 shrink-0" />
          <span v-if="row.kind === 'line'">{{ lineNumberText(row.lineIndex) }}</span>
          <span v-else class="text-[var(--color-text-muted)]">…</span>
        </div>
      </div>

      <!-- 文本区 -->
      <div class="min-h-0 min-w-0 flex-1 overflow-x-auto">
        <div
          ref="contentRootRef"
          class="box-border w-full px-3 font-mono text-[11px] text-[var(--color-text-primary)]"
          :style="verticalPadStyle"
        >
          <div
            v-for="(row, idx) in displayRows"
            :key="'ln-text-' + idx + '-' + row.lineIndex"
            :style="rowStyle"
          >
            <div
              v-if="row.kind === 'line'"
              class="whitespace-pre"
              :style="rowStyle"
            >
              <span
                v-for="(t, ti) in lineTokens(row.lineIndex)"
                :key="ti"
                :class="tokenClass(t.kind)"
              >{{ t.text }}</span>
              <span v-if="lineTokens(row.lineIndex).length === 0">&nbsp;</span>
            </div>
            <button
              v-else
              type="button"
              class="block w-full cursor-pointer whitespace-pre rounded bg-[var(--color-surface-overlay)]/40 px-1 text-left text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-surface-overlay)]"
              :style="rowStyle"
              @click="toggleFold(row.startLine ?? row.lineIndex)"
            >
              … 折叠了 {{ row.foldedLines }} 行
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
