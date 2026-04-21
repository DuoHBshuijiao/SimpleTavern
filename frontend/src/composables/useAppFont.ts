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

/** 用于判断 400/700 是否共用同一套轮廓（单字重静态字体）；可变字体或多字重通常会有可测的宽度差 */
const WEIGHT_PROBE_TEXT = 'Ag 粗斜 MW 0123'

let fontApplyGeneration = 0

/**
 * 在禁用合成的前提下测量文本宽度；若 400 与 700 宽度一致，视为单字重，可对 .prose 启用 font-synthesis 兜底。
 */
function measureTextWidthPx(family: string, fontWeight: number): number {
  const span = document.createElement('span')
  span.textContent = WEIGHT_PROBE_TEXT
  span.style.cssText = [
    'position:absolute',
    'left:-9999px',
    'top:0',
    'visibility:hidden',
    `font-family:"${family}",sans-serif`,
    'font-size:16px',
    `font-weight:${fontWeight}`,
    'font-synthesis:none',
    'white-space:nowrap',
  ].join(';')
  document.body.appendChild(span)
  const w = span.getBoundingClientRect().width
  span.remove()
  return w
}

async function refreshCustomFontSynthesisFlag(expectedGen: number): Promise<void> {
  const root = document.documentElement
  try {
    await document.fonts.load(`16px "${FONT_FAMILY}"`)
  } catch {
    /* 忽略加载失败，后续测量仍可能有效 */
  }
  if (expectedGen !== fontApplyGeneration) return
  await new Promise<void>((r) => requestAnimationFrame(() => r()))
  if (expectedGen !== fontApplyGeneration) return
  const w400 = measureTextWidthPx(FONT_FAMILY, 400)
  const w700 = measureTextWidthPx(FONT_FAMILY, 700)
  if (expectedGen !== fontApplyGeneration) return
  /** 亚像素取整，避免浮点噪声误判 */
  if (Math.round(w400 * 100) === Math.round(w700 * 100)) {
    root.dataset.customFontSingleWeight = 'true'
  } else {
    delete root.dataset.customFontSingleWeight
  }
}

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
export async function applyFont(filename: string | null | undefined) {
  const gen = ++fontApplyGeneration
  const el = ensureStyleElement()
  const root = document.documentElement
  if (!filename) {
    el.textContent = ''
    document.documentElement.style.fontFamily = ''
    document.body.style.fontFamily = ''
    delete root.dataset.customFontSingleWeight
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
  await refreshCustomFontSynthesisFlag(gen)
}

/**
 * 在应用内使用：根据设置中的 selectedFont 自动应用字体，并在设置变更时更新。
 */
export function useAppFont() {
  const settingsStore = useSettingsStore()
  watch(
    () => settingsStore.settings?.selectedFont ?? null,
    (v) => {
      void applyFont(v ?? null).catch(() => {})
    },
    { immediate: true }
  )
  return { applyFont }
}
