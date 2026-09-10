import { defineStore } from 'pinia'

export type SettingsDrawerTab = 'global' | 'presets' | 'chat'

/**
 * 设置抽屉深链（T-822/T-824）：由错误卡片 action 或其他入口发起，
 * SettingsDrawer 打开后按 presetId 切到对应预设并把 field 对应的控件滚入视野、短暂高亮。
 */
export interface SettingsFocusTarget {
  tab: SettingsDrawerTab
  presetId?: string | null
  /** 与控件上的 data-settings-field 对应，如 echoReasoning / reasoningEchoBack / promptCache */
  field?: string | null
}

export const useUiStore = defineStore('ui', {
  state: () => ({
    settingsDrawerRequestNonce: 0,
    requestedSettingsTab: 'global' as SettingsDrawerTab,
    settingsFocusTarget: null as SettingsFocusTarget | null,
    settingsFocusNonce: 0,
  }),
  actions: {
    requestOpenSettings(tab: SettingsDrawerTab = 'global') {
      this.requestedSettingsTab = tab
      this.settingsFocusTarget = null
      this.settingsDrawerRequestNonce += 1
    },
    /** 打开设置并定位到某个预设 / 字段 */
    requestFocusSettings(target: SettingsFocusTarget) {
      this.requestedSettingsTab = target.tab
      this.settingsFocusTarget = { ...target }
      this.settingsFocusNonce += 1
      this.settingsDrawerRequestNonce += 1
    },
    consumeSettingsFocus(): SettingsFocusTarget | null {
      const target = this.settingsFocusTarget
      this.settingsFocusTarget = null
      return target
    },
  },
})
