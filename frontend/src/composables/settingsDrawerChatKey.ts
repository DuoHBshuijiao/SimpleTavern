import type { InjectionKey } from 'vue'

/** Chat Tab 子树 inject 上下文（由 SettingsDrawer provide）。 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type SettingsDrawerChatContext = Record<string, any>

export const SETTINGS_DRAWER_CHAT_KEY: InjectionKey<SettingsDrawerChatContext> =
  Symbol('settingsDrawerChat')
