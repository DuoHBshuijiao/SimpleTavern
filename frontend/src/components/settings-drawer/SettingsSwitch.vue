<script setup lang="ts">
/**
 * 设置页统一的开关行：标签在左、开关在右、说明在下。
 * 开关状态由开关本身表达，不再另写“已开启/已关闭”。
 */
import SettingsField from './SettingsField.vue'

defineProps<{
  label: string
  modelValue: boolean
  hint?: string
  more?: string
  disabled?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()
</script>

<template>
  <SettingsField :label="label" :hint="hint" :more="more">
    <template #actions>
      <button
        type="button"
        role="switch"
        class="settings-switch"
        :class="{ 'settings-switch--on': modelValue }"
        :aria-checked="modelValue"
        :aria-label="label"
        :disabled="disabled"
        @click="emit('update:modelValue', !modelValue)"
      >
        <span class="settings-switch-knob" />
      </button>
    </template>
  </SettingsField>
</template>
