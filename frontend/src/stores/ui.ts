import { defineStore } from 'pinia'

export type SettingsDrawerTab = 'global' | 'presets' | 'chat'

export const useUiStore = defineStore('ui', {
  state: () => ({
    settingsDrawerRequestNonce: 0,
    requestedSettingsTab: 'global' as SettingsDrawerTab,
  }),
  actions: {
    requestOpenSettings(tab: SettingsDrawerTab = 'global') {
      this.requestedSettingsTab = tab
      this.settingsDrawerRequestNonce += 1
    },
  },
})