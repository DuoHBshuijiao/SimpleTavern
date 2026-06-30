import type { InjectionKey } from 'vue'

/** Presets Tab 子树 inject 上下文（由 SettingsDrawer provide）。 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type SettingsDrawerPresetsContext = Record<string, any>

export const SETTINGS_DRAWER_PRESETS_KEY: InjectionKey<SettingsDrawerPresetsContext> =
  Symbol('settingsDrawerPresets')
