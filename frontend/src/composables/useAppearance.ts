import { computed, onScopeDispose, ref, watch } from 'vue'
import { useSettingsStore } from '../stores'
import { useUiStore } from '../stores/ui'
import { normalizeThemeId } from '../types/models'
import { sampleWallpaper } from '../utils/wallpaperScheme.mjs'

type ColorScheme = 'light' | 'dark'

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
