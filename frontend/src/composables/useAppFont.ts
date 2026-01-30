/**
 * useAppFont - 应用自定义字体
 *
 * 根据 settings.selectedFont 注入 @font-face 并设置 body 字体。
 * 字体文件存于 data/fonts，不随备份导出。
 */

import { watch } from 'vue'
import { useSettingsStore } from '../stores'

const STYLE_ID = 'app-custom-font'
const FONT_FAMILY = 'AppCustomFont'

function ensureStyleElement(): HTMLStyleElement {
  let el = document.getElementById(STYLE_ID) as HTMLStyleElement | null
  if (!el) {
    el = document.createElement('style')
    el.id = STYLE_ID
    document.head.appendChild(el)
  }
  return el
}

/**
 * 应用或清除自定义字体
 * @param filename 字体文件名（在 data/fonts 下），null 则恢复默认
 */
export function applyFont(filename: string | null | undefined) {
  const el = ensureStyleElement()
  if (!filename) {
    el.textContent = ''
    document.documentElement.style.fontFamily = ''
    document.body.style.fontFamily = ''
    return
  }
  const url = `/api/fonts/${encodeURIComponent(filename)}`
  const fallback = 'var(--font-sans, ui-sans-serif, system-ui, sans-serif)'
  el.textContent = `
@font-face {
  font-family: "${FONT_FAMILY}";
  src: url("${url}") format("truetype"),
       url("${url}") format("opentype"),
       url("${url}") format("woff"),
       url("${url}") format("woff2");
  font-display: swap;
}
:root, body {
  font-family: "${FONT_FAMILY}", ${fallback} !important;
}
/* 覆盖 #app 内所有文字，确保自定义字体应用于：标题、侧栏、消息气泡、输入框等 */
#app, #app * {
  font-family: "${FONT_FAMILY}", ${fallback} !important;
}
/* 代码块保持等宽字体 */
#app .prose pre, #app .prose code, #app code, #app pre {
  font-family: var(--font-mono) !important;
}
`
}

/**
 * 在应用内使用：根据设置中的 selectedFont 自动应用字体，并在设置变更时更新。
 */
export function useAppFont() {
  const settingsStore = useSettingsStore()
  watch(
    () => settingsStore.settings?.selectedFont ?? null,
    (v) => applyFont(v ?? null),
    { immediate: true }
  )
  return { applyFont }
}
