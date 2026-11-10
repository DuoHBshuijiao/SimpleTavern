<script setup lang="ts">
/**
 * 一个设置项：标签行（可带右侧操作）→ 控件 → 说明。字段自身不带背景和边框。
 * data-settings-field 等属性会落在根元素上，深链定位不受影响。
 *
 * 说明分三档，默认是不写：
 * - 不写：标签、控件和占位文字已经说清楚的，不加任何小字。
 * - 只给 more：ⓘ 跟在标签后面，点开才出现。绝大多数需要解释的项用这一档。
 * - 给 hint：常驻显示，只留给不看就会出错或花钱的事（计费、不可逆、必填前提）。
 */
import { computed, ref } from 'vue'
import { Info } from 'lucide-vue-next'
import SettingsHint from './SettingsHint.vue'

const props = defineProps<{
  label?: string
  /** 常驻的一句短说明，只用于不看就会出错或花钱的事 */
  hint?: string
  /** 收进 ⓘ 的说明 */
  more?: string
}>()

const open = ref(false)
/** 没有常驻说明时，ⓘ 放在标签后面，不单独占一行 */
const moreInHead = computed(() => Boolean(props.more) && !props.hint && Boolean(props.label))
</script>

<template>
  <div class="settings-field">
    <div v-if="label || $slots.actions">
      <div class="settings-field-head">
        <span class="settings-label">
          {{ label }}
          <button
            v-if="moreInHead"
            type="button"
            class="settings-hint-toggle"
            :aria-expanded="open"
            :aria-label="open ? `收起「${label}」的说明` : `查看「${label}」的说明`"
            @click="open = !open"
          >
            <Info class="h-3 w-3" />
          </button>
        </span>
        <slot name="actions" />
      </div>
      <!-- 说明在标签下方展开；和标签包在一起，收起时不会多出一道间距 -->
      <div
        v-if="moreInHead"
        class="settings-hint settings-hint-more"
        :class="{ 'settings-hint-more--open': open }"
      >
        <p class="min-h-0 overflow-hidden">
          <span class="block pb-0.5">{{ more }}</span>
        </p>
      </div>
    </div>
    <slot />
    <SettingsHint v-if="!moreInHead && (hint || more)" :more="more">{{ hint }}</SettingsHint>
    <slot name="after" />
  </div>
</template>
