import { sampleWallpaper } from './wallpaperScheme.mjs'

const { invoke } = window.__TAURI__.core
const { listen } = window.__TAURI__.event
const root = document.documentElement
let current
let request = 0

async function resolveScheme(appearance) {
  if (appearance.mode === 'system') {
    try {
      return await invoke('manager_system_scheme', { revision: appearance.revision }) ? 'light' : 'dark'
    } catch {
      return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
    }
  }
  if (appearance.mode === 'light') return 'light'
  if (!appearance.wallpaper) return 'dark'

  let url
  try {
    const image = await invoke('manager_wallpaper', { revision: appearance.revision })
    url = URL.createObjectURL(new Blob([image]))
    return await sampleWallpaper(url)
  } catch {
    return 'dark'
  } finally {
    if (url) URL.revokeObjectURL(url)
  }
}

async function applyAppearance(appearance) {
  const ticket = ++request
  const scheme = await resolveScheme(appearance)
  if (ticket !== request) return

  root.dataset.applyingAppearance = ''
  root.dataset.theme = appearance.themeId
  root.dataset.colorScheme = scheme
  const canvas = getComputedStyle(root).getPropertyValue('--app-color-surface').trim()
  const background = (canvas.match(/[0-9a-f]{2}/gi) || []).map(channel => parseInt(channel, 16))
  // Resolve the new control styles before re-enabling interaction transitions.
  void document.body.offsetHeight
  delete root.dataset.applyingAppearance
  await invoke('manager_appearance_applied', {
    revision: appearance.revision,
    scheme,
    background: background.length === 3 ? background : scheme === 'light' ? [243, 245, 245] : [21, 18, 23],
  })
}

function reportAppearanceError(error) {
  console.error('Unable to apply manager appearance', error)
}

function receiveAppearance(next) {
  if (current && next.revision <= current.revision) return
  current = next
  return applyAppearance(next).catch(reportAppearanceError)
}

export async function startAppearance() {
  await Promise.all([
    listen('manager-appearance-changed', ({ payload }) => receiveAppearance(payload)),
    listen('tauri://theme-changed', () => {
      if (current?.mode === 'system') void applyAppearance(current).catch(reportAppearanceError)
    }),
  ]).catch(reportAppearanceError)
  await receiveAppearance(await invoke('manager_appearance'))
}
