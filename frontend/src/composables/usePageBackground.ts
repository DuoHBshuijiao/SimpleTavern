import { computed } from 'vue'

import type { Settings } from '../types/models'

type PageBackgroundSource = Pick<
  Settings,
  'pageBackgroundImage' | 'pageBackgroundOpacity' | 'pageBackgroundBlurPx' | 'updatedAt'
>

export function clampPageBackgroundOpacity(value: number | null | undefined): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 1
  return Math.min(1, Math.max(0, value))
}

export function clampPageBackgroundBlurPx(value: number | null | undefined): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 0
  return Math.min(64, Math.max(0, value))
}

export function buildPageBackgroundImageUrl(
  filename: string | null | undefined,
  cacheKey?: string | null | undefined,
): string | null {
  const normalized = filename?.trim()
  if (!normalized) return null
  const base = `/api/page-backgrounds/${encodeURIComponent(normalized)}`
  const normalizedCacheKey = cacheKey?.trim()
  return normalizedCacheKey ? `${base}?v=${encodeURIComponent(normalizedCacheKey)}` : base
}

function pageBackgroundScaleFromBlur(blurPx: number): string {
  if (blurPx <= 0) return 'scale(1)'
  return `scale(${(1 + blurPx / 320).toFixed(3)})`
}

export function usePageBackground(source: () => PageBackgroundSource | null | undefined) {
  const imageUrl = computed(() => buildPageBackgroundImageUrl(source()?.pageBackgroundImage, source()?.updatedAt))
  const opacity = computed(() => clampPageBackgroundOpacity(source()?.pageBackgroundOpacity))
  const blurPx = computed(() => clampPageBackgroundBlurPx(source()?.pageBackgroundBlurPx))
  const imageStyle = computed<Record<string, string>>(() => ({
    opacity: String(opacity.value),
    filter: blurPx.value > 0 ? `blur(${blurPx.value}px)` : 'none',
    transform: pageBackgroundScaleFromBlur(blurPx.value),
  }))

  return {
    blurPx,
    hasImage: computed(() => imageUrl.value !== null),
    imageStyle,
    imageUrl,
    opacity,
  }
}