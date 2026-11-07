<script setup lang="ts">
/**
 * 原地确认的危险按钮：第一次点击变成“确认？”，再点才执行；超时、失焦或按 Esc 恢复。
 * 状态在组件内部，放进 v-memo 的行里也能正常刷新。
 */
import { onBeforeUnmount, ref } from 'vue'

const props = withDefaults(
  defineProps<{
    label?: string
    confirmLabel?: string
    disabled?: boolean
    timeoutMs?: number
  }>(),
  {
    label: '删除',
    confirmLabel: '确认？',
    disabled: false,
    timeoutMs: 3000,
  },
)

const emit = defineEmits<{
  confirm: []
}>()

const armed = ref(false)
let timer: ReturnType<typeof setTimeout> | null = null

function disarm() {
  armed.value = false
  if (timer) {
    clearTimeout(timer)
    timer = null
  }
}

function handleClick() {
  if (!armed.value) {
    armed.value = true
    timer = setTimeout(disarm, props.timeoutMs)
    return
  }
  disarm()
  emit('confirm')
}

onBeforeUnmount(disarm)
</script>

<template>
  <button
    type="button"
    class="btn btn-xs btn-danger inline-confirm"
    :class="{ 'inline-confirm--armed': armed }"
    :disabled="disabled"
    :aria-label="armed ? `确认${label}` : label"
    @click="handleClick"
    @blur="disarm"
    @keydown.esc.stop="disarm"
  >
    {{ armed ? confirmLabel : label }}
  </button>
</template>

<style scoped>
/* 两种文字等宽，变化时旁边的按钮不跳动 */
.inline-confirm {
  min-width: 3.5rem;
}

.inline-confirm--armed,
.inline-confirm--armed:hover:not(:disabled) {
  background-color: color-mix(in srgb, var(--color-error) 68%, var(--color-surface));
  color: #fff;
  box-shadow: none;
}
</style>
