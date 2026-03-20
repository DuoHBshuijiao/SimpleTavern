<script setup lang="ts">
/**
 * App - Vue应用根组件
 *
 * 组件职责：
 * - 作为应用的根组件，提供最外层容器
 * - 渲染路由视图，根据路由配置显示对应页面组件
 * - 根据设置中的 selectedFont 应用自定义字体
 *
 * Props说明：
 * 无（根组件不接收props）
 *
 * Emits说明：
 * 无（根组件不发出事件）
 *
 * 使用的Composables：
 * - useAppFont: 根据 settings.selectedFont 应用字体
 *
 * 使用的Stores：
 * 无（useAppFont 内部使用 settingsStore）
 *
 * 文件关系：
 *    - 被导入：被main.ts导入作为应用根组件
 *    - 导入：导入vue-router的RouterView组件、composables/useAppFont
 *    - 依赖：依赖vue-router
 *    - 位置：应用根组件层，作为所有页面的容器
 */

import { RouterView } from 'vue-router'
import { computed, onUnmounted, watch } from 'vue'
import { useAppFont } from './composables/useAppFont'
import { useSettingsStore } from './stores'
import { normalizeThemeId } from './types/models'

useAppFont()
const settingsStore = useSettingsStore()
const appThemeId = computed(() => normalizeThemeId(settingsStore.settings?.themeId))

watch(
  appThemeId,
  (themeId) => {
    document.documentElement.setAttribute('data-theme', themeId)
    document.body.setAttribute('data-theme', themeId)
  },
  { immediate: true },
)

onUnmounted(() => {
  document.documentElement.removeAttribute('data-theme')
  document.body.removeAttribute('data-theme')
})
</script>

<template>
  <div :data-theme="appThemeId">
    <!-- 路由视图容器：根据路由配置渲染对应的页面组件 -->
    <RouterView />
  </div>
</template>
