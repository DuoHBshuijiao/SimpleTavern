import { computed, onScopeDispose, ref, watch } from 'vue'
import { useSettingsStore } from '../stores'
import { useUiStore } from '../stores/ui'
import { normalizeThemeId } from '../types/models'
import { sampleWallpaper } from '../utils/wallpaperScheme.mjs'

type ColorScheme = 'light' | 'dark'

const APPEARANCE_CACHE_KEY = 'simpletavern:appearanceCache'

interface AppearanceCache {
  themeId: ReturnType<typeof normalizeThemeId>
  colorScheme: ColorScheme
  wallpaperUrl: string | null
}

function readAppearanceCache(): AppearanceCache | null {
  try {
    const raw = localStorage.getItem(APPEARANCE_CACHE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<AppearanceCache>
    if (parsed.colorScheme !== 'light' && parsed.colorScheme !== 'dark') return null
    return {
      themeId: normalizeThemeId(parsed.themeId),
      colorScheme: parsed.colorScheme,
      wallpaperUrl: typeof parsed.wallpaperUrl === 'string' && parsed.wallpaperUrl ? parsed.wallpaperUrl : null,
    }
  } catch {
    return null
  }
}

function writeAppearanceCache(entry: AppearanceCache) {
  try {
    localStorage.setItem(APPEARANCE_CACHE_KEY, JSON.stringify(entry))
  } catch {
    // ignore quota / private mode
  }
}

export function useAppearance() {
  const settings = useSettingsStore()
  const ui = useUiStore()
  const root = document.documentElement
  const cached = readAppearanceCache()
  const system = window.matchMedia('(prefers-color-scheme: light)')
  const systemLight = ref(system.matches)
  const wallpaperScheme = ref<ColorScheme>('dark')
  const cache = new Map<string, Promise<ColorScheme>>()
  const hasAuthoritative = computed(() => Boolean(ui.appearancePreview || settings.settings))
  const mode = computed(() => ui.appearancePreview?.themeMode ?? settings.settings?.themeMode ?? 'dark')
  const theme = computed(() =>
    hasAuthoritative.value
      ? normalizeThemeId(ui.appearancePreview?.themeId ?? settings.settings?.themeId)
      : (cached?.themeId ?? normalizeThemeId(undefined)),
  )
  const wallpaper = computed(() => mode.value === 'background' ? ui.visiblePageBackgroundUrl : null)
  const scheme = computed<ColorScheme>(() => {
    if (!hasAuthoritative.value && cached) return cached.colorScheme
    if (mode.value === 'background') return wallpaperScheme.value
    return mode.value === 'light' || (mode.value === 'system' && systemLight.value) ? 'light' : 'dark'
  })

  const syncSystem = (event: MediaQueryListEvent) => { systemLight.value = event.matches }
  system.addEventListener('change', syncSystem)
  watch(wallpaper, (url, _previous, onCleanup) => {
    wallpaperScheme.value = (url && cached?.wallpaperUrl === url) ? cached.colorScheme : 'dark'
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
    if (settings.settings && !ui.appearancePreview) {
      writeAppearanceCache({
        themeId,
        colorScheme,
        wallpaperUrl: wallpaper.value ?? null,
      })
    }
  }, { immediate: true })

  onScopeDispose(() => {
    system.removeEventListener('change', syncSystem)
    delete root.dataset.theme
    delete root.dataset.colorScheme
  })
}
