<script setup lang="ts">
/**
 * 会话世界书顺序中单本书的扫描深度 / 插入深度编辑（不写回世界书条目）。
 */
import { ref, watch } from 'vue'
import { X } from 'lucide-vue-next'

const props = defineProps<{
  show: boolean
  bookName: string
  scanDepthDefault: number | null | undefined
  scanDepth: number | null
  insertDepth: number
}>()

const emit = defineEmits<{
  'update:show': [boolean]
  save: [payload: { scanDepth: number | null; insertDepth: number }]
}>()

/** 用字符串存，避免 number input 与 trim 混用；也可用 text+inputmode */
const scanStr = ref<string | number>('')
const insertInput = ref(5)

watch(
  () => [props.show, props.scanDepth, props.insertDepth] as const,
  ([open]) => {
    if (!open) return
    if (props.scanDepth != null && props.scanDepth >= 1) {
      scanStr.value = String(props.scanDepth)
    } else {
      scanStr.value = ''
    }
    insertInput.value = props.insertDepth >= 1 ? props.insertDepth : 5
  },
  { immediate: true },
)

const scanPlaceholder = () => {
  const d = props.scanDepthDefault
  if (d != null && d >= 0) return `留空 = 全局默认（${d}）`
  return '留空 = 全局默认'
}

function close() {
  emit('update:show', false)
}

function save() {
  let sd: number | null = null
  // type="number" 的 v-model 可能得到 number，不能对数字调用 .trim()
  const t = String(scanStr.value ?? '').trim()
  if (t !== '' && !Number.isNaN(Number(t))) {
    const n = Math.floor(Number(t))
    sd = n >= 1 ? n : null
  }
  const ins = Math.max(1, Math.floor(Number(insertInput.value) || 5))
  emit('save', { scanDepth: sd, insertDepth: ins })
  emit('update:show', false)
}
</script>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="show" class="modal">
        <div class="modal-backdrop" @click="close"></div>
        <div
          class="modal-content w-[min(92vw,400px)] theme-panel-bg border border-[var(--color-border)] rounded-2xl shadow-xl backdrop-saturate-[1.8]"
          style="backdrop-filter: blur(var(--blur-heavy)); -webkit-backdrop-filter: blur(var(--blur-heavy))"
        >
          <div class="modal-header shrink-0">
            <h3 class="modal-title">会话世界书参数</h3>
            <button type="button" class="modal-close" aria-label="关闭" @click="close">
              <X class="w-5 h-5" />
            </button>
          </div>
          <div class="modal-body space-y-4">
            <p class="text-sm text-[var(--color-text-secondary)] truncate">{{ bookName }}</p>
            <div class="space-y-1.5">
              <label class="text-xs font-medium text-[var(--color-text-secondary)]">扫描深度</label>
              <input
                v-model="scanStr"
                type="text"
                inputmode="numeric"
                pattern="[0-9]*"
                class="input w-full"
                :placeholder="scanPlaceholder()"
              />
              <p class="text-[10px] text-[var(--color-text-muted)]">留空表示与会话全局默认一致；≥1 时对最近 N 条消息做正则匹配。</p>
            </div>
            <div class="space-y-1.5">
              <label class="text-xs font-medium text-[var(--color-text-secondary)]">插入深度</label>
              <input v-model.number="insertInput" type="number" min="1" step="1" class="input w-full" />
            </div>
          </div>
          <div class="modal-footer shrink-0">
            <button type="button" class="btn btn-secondary" @click="close">取消</button>
            <button type="button" class="btn btn-primary" @click="save">保存</button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
