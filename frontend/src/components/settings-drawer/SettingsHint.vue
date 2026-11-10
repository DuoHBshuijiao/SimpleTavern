<script setup lang="ts">
/**
 * 设置说明。全部设置页共用这一种写法，不要再单独写说明文字的样式。
 *
 * - 默认插槽：常驻的一句短说明。只留给不看就会出错或花钱的事，其余不要常驻。
 * - more：收进 ⓘ，点开才出现。
 * - title：分组标题。给了 title 就由本组件渲染标题，ⓘ 跟在标题后面，说明在标题下方展开。
 *
 * 单个设置项的说明用 SettingsField 的 hint / more，不要在字段外面再放一个 SettingsHint。
 */
import { ref } from 'vue'
import { Info } from 'lucide-vue-next'

defineProps<{
  /** 收进 ⓘ 的说明 */
  more?: string
  /** 分组标题；ⓘ 跟在标题后面 */
  title?: string
}>()

const open = ref(false)
</script>

<template>
  <div v-if="title">
    <div class="settings-group-title">
      {{ title }}
      <button
        v-if="more"
        type="button"
        class="settings-hint-toggle"
        :aria-expanded="open"
        :aria-label="open ? `收起「${title}」的说明` : `查看「${title}」的说明`"
        @click="open = !open"
      >
        <Info class="h-3 w-3" />
      </button>
    </div>
    <div v-if="more" class="settings-hint settings-hint-more" :class="{ 'settings-hint-more--open': open }">
      <p class="min-h-0 overflow-hidden">
        <span class="block pt-1">{{ more }}</span>
      </p>
    </div>
  </div>
  <div v-else class="settings-hint">
    <p>
      <slot />
      <button
        v-if="more"
        type="button"
        class="settings-hint-toggle"
        :aria-expanded="open"
        :aria-label="open ? '收起说明' : '展开说明'"
        @click="open = !open"
      >
        <Info class="h-3 w-3" />
      </button>
    </p>
    <div v-if="more" class="settings-hint-more" :class="{ 'settings-hint-more--open': open }">
      <p class="min-h-0 overflow-hidden">
        <span class="block pt-1">{{ more }}</span>
      </p>
    </div>
  </div>
</template>
