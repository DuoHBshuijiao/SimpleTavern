<script setup lang="ts">
/**
 * 一个设置项：标签行（可带右侧操作）→ 控件 → 说明。字段自身不带背景和边框。
 * data-settings-field 等属性会落在根元素上，深链定位不受影响。
 */
import SettingsHint from './SettingsHint.vue'

defineProps<{
  label?: string
  /** 一句短说明 */
  hint?: string
  /** 长说明，收进 ⓘ */
  more?: string
}>()
</script>

<template>
  <div class="settings-field">
    <div v-if="label || $slots.actions" class="settings-field-head">
      <span class="settings-label">{{ label }}</span>
      <slot name="actions" />
    </div>
    <slot />
    <SettingsHint v-if="hint || more" :more="more">{{ hint }}</SettingsHint>
    <slot name="after" />
  </div>
</template>
