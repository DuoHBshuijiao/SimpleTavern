import { computed, onScopeDispose, ref, watch } from 'vue'
import { useSettingsStore } from '../stores'
import { useUiStore } from '../stores/ui'
import { normalizeThemeId } from '../types/models'

type ColorScheme = 'light' | 'dark'

const linearSrgb = Array.from({ length: 256 }, (_, value) => {
  const channel = value / 255
  return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4
})

async function sampleWallpaper(url: string): Promise<ColorScheme> {
  const image = new Image()
  image.src = url
  await image.decode()

  const scale = Math.min(1, 64 / Math.max(image.naturalWidth, image.naturalHeight))
  const canvas = document.createElement('canvas')
  canvas.width = Math.max(1, Math.round(image.naturalWidth * scale))
  canvas.height = Math.max(1, Math.round(image.naturalHeight * scale))
  const context = canvas.getContext('2d', { willReadFrequently: true })
  if (!context) return 'dark'
  context.drawImage(image, 0, 0, canvas.width, canvas.height)
  const { data } = context.getImageData(0, 0, canvas.width, canvas.height)
  const samples: { lightness: number; weight: number }[] = []
  let totalWeight = 0
  for (let i = 0; i < data.length; i += 4) {
    const weight = data[i + 3]!
    if (!weight) continue
    const luminance = 0.2126 * linearSrgb[data[i]!]! + 0.7152 * linearSrgb[data[i + 1]!]!
      + 0.0722 * linearSrgb[data[i + 2]!]!
    const lightness = luminance > 216 / 24389 ? 116 * Math.cbrt(luminance) - 16 : luminance * (24389 / 27)
    totalWeight += weight
    samples.push({ lightness, weight })
  }
  if (!totalWeight) return 'dark'

  samples.sort((a, b) => a.lightness - b.lightness)
  const lower = totalWeight * 0.1
  const upper = totalWeight * 0.9
  let position = 0
  let sum = 0
  for (const sample of samples) {
    const end = position + sample.weight
    const weight = Math.max(0, Math.min(end, upper) - Math.max(position, lower))
    sum += sample.lightness * weight
    position = end
  }
  return sum / (upper - lower) >= 58 ? 'light' : 'dark'
}

export function useAppearance() {
  const settings = useSettingsStore()
  const ui = useUiStore()
  const root = document.documentElement
  const system = window.matchMedia('(prefers-color-scheme: light)')
  const systemLight = ref(system.matches)
  const wallpaperScheme = ref<ColorScheme>('dark')
  const cache = new Map<string, Promise<ColorScheme>>()
  const mode = computed(() => ui.appearancePreview?.themeMode ?? settings.settings?.themeMode ?? 'dark')
  const theme = computed(() => normalizeThemeId(ui.appearancePreview?.themeId ?? settings.settings?.themeId))
  const wallpaper = computed(() => mode.value === 'background' ? ui.visiblePageBackgroundUrl : null)
  const scheme = computed<ColorScheme>(() => {
    if (mode.value === 'background') return wallpaperScheme.value
    return mode.value === 'light' || (mode.value === 'system' && systemLight.value) ? 'light' : 'dark'
  })

  const syncSystem = (event: MediaQueryListEvent) => { systemLight.value = event.matches }
  system.addEventListener('change', syncSystem)
  watch(wallpaper, (url, _previous, onCleanup) => {
    wallpaperScheme.value = 'dark'
    if (!url) return
    let current = true
    onCleanup(() => { current = false })
    let sample = cache.get(url)
    if (!sample) {
      sample = sampleWallpaper(url).catch(() => 'dark' as const)
      if (cache.size >= 32) cache.delete(cache.keys().next().value!)
      cache.set(url, sample)
    }
    void sample.then((result) => {
      if (current && wallpaper.value === url) wallpaperScheme.value = result
    })
  }, { immediate: true })

  watch([theme, scheme], ([themeId, colorScheme]) => {
    root.dataset.theme = themeId
    root.dataset.colorScheme = colorScheme
  }, { immediate: true })

  onScopeDispose(() => {
    system.removeEventListener('change', syncSystem)
    delete root.dataset.theme
    delete root.dataset.colorScheme
  })
}
